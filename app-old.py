import os
import random
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from supabase import create_client, Client
from functools import wraps

# .env 파일에서 환경 변수 로드
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Supabase 클라이언트 초기화
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

if not url or not key:
    raise ValueError("Supabase URL 또는 Key가 .env 파일에 설정되지 않았습니다.")

supabase: Client = create_client(url, key)

# --- Helper Functions ---

def format_datetime_filter(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            value = value.replace('Z', '+00:00')
            if '+' in value and ':' not in value[value.rfind('+'):]:
                offset = value[value.rfind('+'):]
                value = value[:value.rfind('+')] + offset[:3] + ':' + offset[3:]
            dt_object = datetime.fromisoformat(value)
        elif isinstance(value, datetime):
            dt_object = value
        else:
            return value
        return dt_object.strftime(format)
    except (ValueError, TypeError, AttributeError) as e:
        print(f"Error formatting datetime '{value}': {e}")
        return value

app.jinja_env.filters['format_datetime'] = format_datetime_filter

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Sila log masuk untuk mengakses halaman ini.", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

@app.route('/')
def home():
    user = session.get('user')
    username = session.get('username')
    return render_template('home.html', user=user, username=username)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        church_code = request.form.get('church_code')
        username = request.form.get('username')
        password = request.form.get('password')

        print(f"Signup attempt - church_code: {church_code}, username: {username}")

        if not church_code or not username or not password:
            flash("Sila masukkan Kod Gereja, Nama Pengguna dan Kata Laluan.", "error")
            return redirect(url_for('signup'))

        if len(password) < 6:
            flash("Kata laluan mesti sekurang-kurangnya 6 aksara.", "error")
            return redirect(url_for('signup'))

        email = f"{username}-{church_code}@quizapp.local"
        print(f"Generated email: {email}")

        try:
            # 1. 중복 확인
            existing_profile = supabase.table('profiles') \
                .select('id', count='exact') \
                .eq('church_code', church_code) \
                .eq('username', username) \
                .execute()

            print(f"Existing profile check: {existing_profile}")

            if existing_profile.count > 0:
                flash("Nama pengguna ini sudah wujud untuk kod gereja ini.", "error")
                return redirect(url_for('signup'))

            # 2. Supabase auth 등록
            res = supabase.auth.sign_up({
                "email": email,
                "password": password,
            })

            if not res.user or not res.user.id:
                flash("Pendaftaran gagal (Auth). Sila cuba lagi.", "error")
                return redirect(url_for('signup'))

            user_id = res.user.id

            # 3. profiles 테이블에 삽입
            profile_data = {
                'id': str(user_id),
                'church_code': church_code,
                'username': username,
                'email': email,
                'phone': None
            }
            print(f"Inserting profile: {profile_data}")
            supabase.table('profiles').insert(profile_data).execute()

            # 4. 자동 로그인
            login_res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if login_res.user and login_res.session:
                session.clear()
                session['user'] = login_res.user.model_dump()
                session['access_token'] = login_res.session.access_token
                session['username'] = username
                session['church_code'] = church_code
                flash("Pendaftaran dan log masuk berjaya!", "success")
                return redirect(url_for('home'))
            else:
                flash("Pendaftaran berjaya! Sila log masuk.", "success")
                return redirect(url_for('login'))

        except Exception as e:
            error_message = str(e)
            print(f"Signup error: {error_message}")
            if "23505" in error_message:
                flash("Nama pengguna ini sudah wujud untuk kod gereja ini.", "error")
            else:
                flash(f"Pendaftaran gagal: {error_message}", "error")
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        church_code = request.form.get('church_code')
        username = request.form.get('username')
        password = request.form.get('password')

        print(f"Login attempt - church_code: {church_code}, username: {username}")

        if not church_code or not username or not password:
            flash("Sila masukkan Kod Gereja, Nama Pengguna dan Kata Laluan.", "error")
            return redirect(url_for('login'))

        try:
            # 1. profiles에서 이메일 조회
            email = f"{username}-{church_code}@quizapp.local"
            print(f"Generated email for login: {email}")

            profile_response = supabase.table('profiles') \
                .select('id, email, church_code, username') \
                .eq('email', email) \
                .execute()

            print(f"Profile query response: {profile_response}")

            if not profile_response.data or len(profile_response.data) == 0:
                flash("Kod Gereja atau Nama Pengguna tidak dijumpai.", "error")
                return redirect(url_for('login'))

            profile = profile_response.data[0]
            print(f"Found profile: {profile}")

            # 2. Supabase auth로 로그인
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            print(f"Auth response: {res}")

            if res.user and res.session:
                session.clear()
                session['user'] = res.user.model_dump()
                session['access_token'] = res.session.access_token
                session['username'] = username
                session['church_code'] = church_code
                flash("Log masuk berjaya!", "success")
                next_url = request.args.get('next')
                return redirect(next_url or url_for('home'))
            else:
                flash("Kata laluan salah. 비밀번호를 잊으셨다면 관리자에게 문의하세요.", "error")
                return redirect(url_for('login'))

        except Exception as e:
            error_message = str(e)
            print(f"Login error: {error_message}")
            flash(f"Log masuk gagal: {error_message}", "error")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    try:
        supabase.auth.sign_out()
    except Exception as e:
        pass
    session.clear()
    flash("Anda telah berjaya log keluar.", "success")
    return redirect(url_for('home'))

@app.route('/select-book')
@login_required
def select_book():
    try:
        response = supabase.table('bible_books').select('id, name').order('id').execute()
        books = response.data if response and hasattr(response, 'data') else []
        return render_template('select_book.html', books=books)
    except Exception as e:
        flash(f"Gagal memuatkan senarai kitab: {e}", "error")
        print(f"Error fetching book list: {e}")
        return redirect(url_for('home'))

@app.route('/quiz/<int:book_id>')
@login_required
def quiz(book_id):
    try:
        book_response = supabase.table('bible_books').select('name').eq('id', book_id).single().execute()
        if not book_response or not book_response.data:
            flash("Kitab tidak dijumpai.", "error")
            return redirect(url_for('select_book'))
        book_name = book_response.data['name']

        questions_response = supabase.table('questions') \
            .select('id, question_text, option_a, option_b, option_c, option_d, correct_answer') \
            .eq('book_id', book_id) \
            .execute()
        questions = questions_response.data if questions_response and hasattr(questions_response, 'data') else []

        if not questions:
            flash("Tiada soalan untuk kitab ini.", "error")
            return redirect(url_for('select_book'))

        MAX_QUESTIONS = 20
        total_questions = min(len(questions), MAX_QUESTIONS)
        if len(questions) > MAX_QUESTIONS:
            questions = random.sample(questions, MAX_QUESTIONS)

        return render_template('quiz.html', questions=questions, book_id=book_id, total_questions=total_questions, book_name=book_name)
    except Exception as e:
        flash(f"Gagal memuatkan kuiz: {e}", "error")
        print(f"Error loading quiz: {e}")
        return redirect(url_for('select_book'))

@app.route('/submit-answer', methods=['POST'])
@login_required
def submit_answer():
    data = request.get_json()
    question_id = data.get('question_id')
    user_answer = data.get('answer')

    if not question_id:
        return jsonify({'error': 'Question ID is missing'}), 400

    try:
        question_response = supabase.table('questions').select('correct_answer').eq('id', question_id).single().execute()
        if not question_response or not question_response.data:
            return jsonify({'error': 'Question not found'}), 404

        correct_answer = question_response.data['correct_answer']
        is_correct = (user_answer == correct_answer)

        return jsonify({'correct': is_correct, 'correct_answer': correct_answer})

    except Exception as e:
        print(f"Error checking answer: {e}")
        return jsonify({'error': f'An error occurred: {e}'}), 500

@app.route('/complete-quiz', methods=['POST'])
@login_required
def complete_quiz():
    data = request.get_json()
    print(f"Received data: {data}")

    if not data:
        return jsonify({'success': False, 'message': 'No data received from client'}), 400

    book_id = data.get('book_id')
    final_score = data.get('score')
    total_questions = data.get('total_questions')

    print(f"book_id: {book_id}, score: {final_score}, total_questions: {total_questions}")

    user_info = session.get('user')
    if not user_info or 'id' not in user_info:
        return jsonify({'success': False, 'message': 'Sesi pengguna tidak sah.', 'redirect': url_for('login')}), 401

    user_id = user_info['id']

    # 데이터 검증
    if book_id is None:
        return jsonify({'success': False, 'message': 'Book ID is missing'}), 400
    if final_score is None:
        return jsonify({'success': False, 'message': 'Score is missing'}), 400
    if total_questions is None:
        return jsonify({'success': False, 'message': 'Total questions is missing'}), 400

    # 데이터 타입 변환
    try:
        book_id = int(book_id)
        final_score = int(final_score)
        total_questions = int(total_questions)
    except (ValueError, TypeError) as e:
        print(f"Data type conversion error: {e}")
        return jsonify({'success': False, 'message': f'Invalid data types: {str(e)}'}), 400

    try:
        # scores 테이블에 저장
        score_response = supabase.table('scores').insert({
            'user_id': user_id,
            'book_id': book_id,
            'score': final_score
        }).execute()
        print(f"Score insert response: {score_response}")

        # leaderboard 업데이트
        existing_leaderboard = supabase.table('leaderboard') \
            .select('score') \
            .eq('book_id', book_id) \
            .eq('user_id', user_id) \
            .execute()

        print(f"Existing leaderboard: {existing_leaderboard}")

        current_leaderboard_score = existing_leaderboard.data[0]['score'] if existing_leaderboard.data and len(existing_leaderboard.data) > 0 else 0

        if not existing_leaderboard.data or final_score > current_leaderboard_score:
            leaderboard_response = supabase.table('leaderboard').upsert({
                'book_id': book_id,
                'user_id': user_id,
                'username': session.get('username'),
                'score': final_score
            }).execute()
            print(f"Leaderboard upsert response: {leaderboard_response}")

        return jsonify({
            'success': True,
            'message': 'Skor berjaya disimpan.',
            'score': final_score,
            'total_questions': total_questions,
            'redirect': url_for('results', score=final_score, book_id=book_id, total_questions=total_questions)
        })

    except Exception as e:
        error_message = str(e)
        print(f"Error saving score: {error_message}")
        return jsonify({'success': False, 'message': f'Gagal menyimpan skor: {error_message}'}), 500

@app.route('/results')
@login_required
def results():
    score = request.args.get('score', type=int)
    book_id = request.args.get('book_id', type=int)
    total_questions = request.args.get('total_questions', type=int)
    book_name = "Kitab Tidak Diketahui"
    current_score = 0

    if book_id is not None:
        try:
            book_response = supabase.table('bible_books').select('name').eq('id', book_id).single().execute()
            if book_response and book_response.data:
                book_name = book_response.data['name']

            user_id = session.get('user')['id']
            leaderboard_response = supabase.table('leaderboard') \
                .select('score') \
                .eq('book_id', book_id) \
                .eq('user_id', user_id) \
                .execute()
            if leaderboard_response.data and len(leaderboard_response.data) > 0:
                current_score = leaderboard_response.data[0]['score']

        except Exception as e:
            print(f"Error fetching book name or leaderboard for results page: {e}")
            flash(f"Gagal memuatkan maklumat: {e}", "error")

    if score is None or book_id is None or total_questions is None:
        flash("Maklumat skor tidak lengkap.", "warning")
        return redirect(url_for('select_book'))

    return render_template('results.html', score=score, book_id=book_id, book_name=book_name, total_questions=total_questions, current_score=current_score)

@app.route('/my-scores')
@login_required
def my_scores():
    user_info = session.get('user')
    if not user_info or 'id' not in user_info:
        flash("Sesi pengguna tidak sah. Sila log masuk semula.", "error")
        return redirect(url_for('login'))
    user_id = user_info['id']

    try:
        response = supabase.table('scores') \
            .select('score, achieved_at, bible_books(name)') \
            .eq('user_id', user_id) \
            .order('achieved_at', desc=True) \
            .execute()
        print(f"My scores response: {response}")
        scores_data = response.data if response and hasattr(response, 'data') else []
        return render_template('my_scores.html', scores=scores_data)
    except Exception as e:
        flash(f"Gagal memuatkan skor peribadi: {e}", "error")
        print(f"Error fetching personal scores: {e}")
        return redirect(url_for('select_book'))

@app.route('/leaderboard/<int:book_id>')
@login_required
def leaderboard(book_id):
    try:
        book_response = supabase.table('bible_books').select('name').eq('id', book_id).single().execute()
        if not book_response or not book_response.data:
            flash("Kitab tidak dijumpai.", "error")
            return redirect(url_for('select_book'))
        book_name = book_response.data['name']

        leaderboard_response = supabase.table('leaderboard') \
            .select('username, score') \
            .eq('book_id', book_id) \
            .order('score', desc=True) \
            .limit(10) \
            .execute()
        leaderboard_data = leaderboard_response.data if leaderboard_response and hasattr(leaderboard_response, 'data') else []

        return render_template('leaderboard.html', leaderboard=leaderboard_data, book_name=book_name, book_id=book_id)

    except Exception as e:
        flash(f"Gagal memuatkan papan pendahulu: {e}", "error")
        print(f"Error fetching leaderboard: {e}")
        return redirect(url_for('select_book'))

# --- Run Application ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)