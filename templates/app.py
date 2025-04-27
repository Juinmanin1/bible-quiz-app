import os
import random
import logging
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from supabase import create_client, Client
from functools import wraps

# Configure logging
logging.basicConfig(level=logging.DEBUG)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase = None
if not url or not key:
    print("SUPABASE_URL or SUPABASE_KEY are not set in the .env file. Supabase features will be unavailable.")
else:
    try:
        supabase: Client = create_client(url, key)
    except Exception as e:
        print(f"Failed to create Supabase client: {e}")
        supabase = None

def supabase_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if supabase is None:
            flash("Aplikasi tidak dapat berhubung dengan pangkalan data (Supabase tidak tersedia). Sila cuba sebentar lagi atau hubungi pentadbir.", "error")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def format_datetime_filter(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        return ""
    try:
        if isinstance(value, str):
            try:
                dt_object = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                print(f"Could not parse '{value}' as ISO 8601. Returning original.")
                return value
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

@app.route('/')
def home():
    user = session.get('user')
    username = session.get('username')
    return render_template('home.html', user=user, username=username)

@app.route('/signup', methods=['GET', 'POST'])
@supabase_required
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
            existing_profile = supabase.table('profiles') \
                .select('id', count='exact') \
                .eq('church_code', church_code) \
                .eq('username', username) \
                .execute()

            print(f"Existing profile check: {existing_profile}")

            if existing_profile.count > 0:
                flash("Nama pengguna ini sudah wujud untuk kod gereja ini.", "error")
                return redirect(url_for('signup'))

            res = supabase.auth.sign_up({
                "email": email,
                "password": password,
            })

            if not res.user or not res.user.id:
                flash("Pendaftaran gagal (Supabase Auth). Sila cuba lagi.", "error")
                print(f"Supabase Auth signup failed: {res.error}")
                return redirect(url_for('signup'))

            user_id = res.user.id

            profile_data = {
                'id': str(user_id),
                'church_code': church_code,
                'username': username,
                'email': email,
                'phone': None
            }
            print(f"Inserting profile: {profile_data}")
            supabase.table('profiles').insert(profile_data).execute()

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
                flash("Pendaftaran berjaya! Sila log masuk secara manual.", "success")
                print(f"Automatic login failed after signup: {login_res.error}")
                return redirect(url_for('login'))

        except Exception as e:
            error_message = str(e)
            print(f"Signup error: {error_message}")
            if "duplicate key value violates unique constraint" in error_message or "23505" in error_message:
                flash("Nama pengguna ini sudah wujud untuk kod gereja ini.", "error")
            else:
                flash(f"Pendaftaran gagal: {error_message}", "error")

            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
@supabase_required
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
            email = f"{username}-{church_code}@quizapp.local"
            print(f"Generated email for login: {email}")

            profile_response = supabase.table('profiles') \
                .select('id, email, church_code, username') \
                .eq('email', email) \
                .execute()

            print(f"Profile query response: {profile_response}")
            print(f"Profile query data: {profile_response.data}")

            if not profile_response.data or len(profile_response.data) == 0:
                print(f"DEBUG: Profile not found for email: {email}")
                flash("Kod Gereja atau Nama Pengguna tidak dijumpai.", "error")
                return redirect(url_for('login'))

            profile = profile_response.data[0]
            print(f"Found profile: {profile}")

            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            print(f"Auth response: {res}")
            print(f"DEBUG: Auth response user: {res.user}")
            print(f"DEBUG: Auth response session: {res.session}")
            print(f"DEBUG: Auth response error: {res.error}")

            if res.user and res.session:
                session.clear()
                session['user'] = res.user.model_dump()
                session['access_token'] = res.session.access_token
                session['username'] = profile['username']
                session['church_code'] = profile['church_code']

                flash("Log masuk berjaya!", "success")

                next_url = request.args.get('next')
                return redirect(next_url or url_for('home'))
            else:
                print(f"DEBUG: Supabase Auth signin failed for email: {email}")
                flash("Kata laluan salah. Jika anda terlupa kata laluan, sila hubungi pentadbir.", "error")
                print(f"Supabase Auth signin failed: {res.error}")
                return redirect(url_for('login'))

        except Exception as e:
            error_message = str(e)
            print(f"Login error: {error_message}")
            print(f"DEBUG: Exception occurred during login: {e}")
            flash(f"Log masuk gagal: {error_message}", "error")
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    try:
        if supabase:
            supabase.auth.sign_out()
            print("Supabase user signed out.")
        else:
            print("Supabase client not available, skipping Supabase sign out.")
    except Exception as e:
        print(f"Error during Supabase sign out: {e}")
        pass

    session.clear()
    print("Flask session cleared.")
    flash("Anda telah berjaya log keluar.", "success")
    return redirect(url_for('home'))

@app.route('/select-book')
@login_required
@supabase_required
def select_book():
    try:
        response = supabase.table('bible_books') \
            .select('id, name') \
            .order('id', desc=False) \
            .execute()
        books = response.data if response and hasattr(response, 'data') else []
        return render_template('select_book.html', books=books)
    except Exception as e:
        flash(f"Gagal memuatkan senarai kitab: {e}", "error")
        print(f"Error fetching book list: {e}")
        return redirect(url_for('home'))

@app.route('/quiz/<int:book_id>')
@login_required
@supabase_required
def quiz(book_id):
    try:
        book_response = supabase.table('bible_books') \
            .select('name') \
            .eq('id', book_id) \
            .single() \
            .execute()
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
        random.shuffle(questions)

        return render_template('quiz.html',
                               questions=questions,
                               book_id=book_id,
                               total_questions=total_questions,
                               book_name=book_name)
    except Exception as e:
        flash(f"Gagal memuatkan kuiz: {e}", "error")
        print(f"Error loading quiz: {e}")
        return redirect(url_for('select_book'))

@app.route('/submit-answer', methods=['POST'])
@login_required
@supabase_required
def submit_answer():
    data = request.get_json()
    question_id = data.get('question_id')
    user_answer = data.get('answer')

    if not question_id:
        return jsonify({'error': 'Question ID is missing'}), 400

    try:
        question_response = supabase.table('questions') \
            .select('correct_answer') \
            .eq('id', question_id) \
            .single() \
            .execute()
        if not question_response or not question_response.data:
            return jsonify({'error': 'Question not found'}), 404

        correct_answer = question_response.data['correct_answer']
        is_correct = (user_answer == correct_answer)

        return jsonify({'correct': is_correct, 'correct_answer': correct_answer})

    except Exception as e:
        print(f"Error checking answer: {e}")
        error_message = str(e)
        return jsonify({'error': f'An error occurred: {error_message}'}), 500

@app.route('/complete-quiz', methods=['POST'])
@login_required
@supabase_required
def complete_quiz():
    data = request.get_json()
    print(f"Received data: {data}")

    required_fields = ['book_id', 'score', 'total_questions']
    if not all(field in data and data[field] is not None for field in required_fields):
        missing_fields = [field for field in required_fields if field not in data or data[field] is None]
        print(f"Missing or null fields: {missing_fields}")
        return jsonify({'success': False, 'message': f'Data tidak lengkap. Medan hilang: {", ".join(missing_fields)}'}), 400

    book_id = data['book_id']
    final_score = data['score']
    total_questions = data['total_questions']

    print(f"book_id: {book_id}, score: {final_score}, total_questions: {total_questions}")

    user_info = session.get('user')
    if not user_info or 'id' not in user_info:
        return jsonify({'success': False, 'message': 'Sesi pengguna tidak sah.', 'redirect': url_for('login')}), 401

    user_id = user_info['id']
    username = session.get('username')

    try:
        book_id = int(book_id)
        final_score = int(final_score)
        total_questions = int(total_questions)
        if final_score < 0 or final_score > total_questions:
            return jsonify({'success': False, 'message': 'Skor tidak sah. Skor mestilah antara 0 dan Jumlah Soalan.'}), 400

    except (ValueError, TypeError) as e:
        print(f"Data type conversion error: {e}")
        return jsonify({'success': False, 'message': f'Jenis data tidak sah untuk book_id, score, atau total_questions: {str(e)}'}), 400

    try:
        # Save score to 'scores' table (always insert new record)
        score_data = {
            'user_id': user_id,
            'book_id': book_id,
            'score': final_score,
            'achieved_at': datetime.utcnow().isoformat()
        }
        print(f"Attempting to insert into scores: {score_data}")
        score_response = supabase.table('scores').insert(score_data).execute()
        print(f"Score insert response: {score_response}")

        if not score_response.data:
            print("Failed to insert score into 'scores' table. Check RLS policies or constraints.")
            error_detail = getattr(score_response, 'error', 'Unknown error')
            print(f"Score insert error detail: {error_detail}")
            # Continue to update leaderboard even if score insertion fails

        # Update leaderboard with the highest score
        existing_leaderboard = supabase.table('leaderboard') \
            .select('score') \
            .eq('book_id', book_id) \
            .eq('user_id', user_id) \
            .execute()

        print(f"Existing leaderboard check: {existing_leaderboard}")

        current_leaderboard_score = 0
        if existing_leaderboard and existing_leaderboard.data and len(existing_leaderboard.data) > 0:
            current_leaderboard_score = existing_leaderboard.data[0].get('score', 0)
            print(f"Found existing leaderboard score: {current_leaderboard_score}")
        else:
            print("No existing leaderboard entry found for this user and book.")

        if final_score >= current_leaderboard_score:
            print(f"New score ({final_score}) is greater than or equal to current leaderboard score ({current_leaderboard_score}). Upserting leaderboard...")
            leaderboard_data = {
                'book_id': book_id,
                'user_id': user_id,
                'username': username,
                'score': final_score,
                'updated_at': datetime.utcnow().isoformat()
            }
            print(f"Attempting to upsert into leaderboard: {leaderboard_data}")
            leaderboard_response = supabase.table('leaderboard').upsert(leaderboard_data).execute()
            print(f"Leaderboard upsert response: {leaderboard_response}")

            if not leaderboard_response.data:
                print("Failed to upsert leaderboard. Check database constraints or RLS policies.")
                return jsonify({
                    'success': False,
                    'message': 'Skor anda telah disimpan, tetapi gagal mengemas kini papan pendahulu. Sila hubungi pentadbir jika masalah ini berterusan.'
                }), 500
        else:
            print(f"New score ({final_score}) is less than current leaderboard score ({current_leaderboard_score}). No leaderboard update needed.")

        return jsonify({
            'success': True,
            'message': 'Skor anda telah berjaya disimpan!',
            'score': final_score,
            'total_questions': total_questions,
            'redirect': url_for('results', score=final_score, book_id=book_id, total_questions=total_questions)
        })

    except Exception as e:
        error_message = str(e)
        print(f"Error saving score: {error_message}")
        if "23505" in error_message:
            print("Duplicate key error on scores table. Attempting to update leaderboard anyway...")
            # Update leaderboard even if score insertion fails due to duplicate
            existing_leaderboard = supabase.table('leaderboard') \
                .select('score') \
                .eq('book_id', book_id) \
                .eq('user_id', user_id) \
                .execute()

            current_leaderboard_score = 0
            if existing_leaderboard and existing_leaderboard.data and len(existing_leaderboard.data) > 0:
                current_leaderboard_score = existing_leaderboard.data[0].get('score', 0)

            if final_score >= current_leaderboard_score:
                leaderboard_data = {
                    'book_id': book_id,
                    'user_id': user_id,
                    'username': username,
                    'score': final_score,
                    'updated_at': datetime.utcnow().isoformat()
                }
                leaderboard_response = supabase.table('leaderboard').upsert(leaderboard_data).execute()
                if leaderboard_response.data:
                    return jsonify({
                        'success': True,
                        'message': 'Skor anda telah disimpan (sebelumnya), dan papan pendahulu telah dikemas kini.',
                        'score': final_score,
                        'total_questions': total_questions,
                        'redirect': url_for('results', score=final_score, book_id=book_id, total_questions=total_questions)
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Gagal mengemas kini papan pendahulu. Sila hubungi pentadbir.'
                    }), 500
            else:
                return jsonify({
                    'success': True,
                    'message': 'Skor anda telah disimpan (sebelumnya), tetapi papan pendahulu는 갱신되지 않았습니다 (현재 점수가 더 높음).',
                    'score': final_score,
                    'total_questions': total_questions,
                    'redirect': url_for('results', score=final_score, book_id=book_id, total_questions=total_questions)
                })
        elif "42501" in error_message:
            display_message = "Skor anda telah disimpan, tetapi gagal mengemas kini papan pendahulu kerana isu kebenaran RLS. Sila hubungi pentadbir."
            print("RLS Policy error detected on leaderboard update. Check Supabase RLS settings.")
        else:
            display_message = f'Skor anda telah disimpan, tetapi gagal mengemas kini papan pendahulu: {error_message}'
        return jsonify({'success': False, 'message': display_message}), 500

@app.route('/results')
@login_required
@supabase_required
def results():
    print("Entering /results endpoint")
    
    # Extract query parameters
    score = request.args.get('score', type=int)
    book_id = request.args.get('book_id', type=int)
    total_questions = request.args.get('total_questions', type=int)

    print(f"Raw query parameters - score: {request.args.get('score')}, book_id: {request.args.get('book_id')}, total_questions: {request.args.get('total_questions')}")
    print(f"Parsed query parameters - score: {score}, book_id: {book_id}, total_questions: {total_questions}")

    # Validate query parameters
    if score is None or book_id is None or total_questions is None:
        flash("Maklumat keputusan kuiz tidak lengkap.", "warning")
        print(f"Missing query parameters - score: {score}, book_id: {book_id}, total_questions: {total_questions}")
        return redirect(url_for('select_book'))

    if total_questions <= 0:
        flash("Kuiz ini tidak mempunyai soalan yang sah.", "warning")
        print(f"Total questions is zero or negative - book_id: {book_id}, total_questions: {total_questions}")
        return redirect(url_for('select_book'))

    # Initialize default values
    book_name = "Kitab Tidak Diketahui"
    current_highest_score = 0

    # Validate user session
    user_info = session.get('user')
    if not user_info or 'id' not in user_info:
        flash("Sesi pengguna tidak sah.", "error")
        print("User session invalid or missing.")
        return redirect(url_for('login'))
    user_id = user_info['id']
    print(f"User session validated - user_id: {user_id}")

    # Fetch book name
    try:
        book_response = supabase.table('bible_books') \
            .select('name') \
            .eq('id', book_id) \
            .single() \
            .execute()
        print(f"Book query response: {book_response}")
        print(f"Book query data: {book_response.data if book_response else None}")
        print(f"Book query error: {getattr(book_response, 'error', None)}")
        if book_response and hasattr(book_response, 'data') and book_response.data:
            book_name = book_response.data.get('name', "Kitab Tidak Diketahui")
        else:
            print(f"No book found for book_id: {book_id}")
    except Exception as e:
        print(f"Error fetching book name: {e}")
        book_name = "Kitab Tidak Diketahui"

    # Fetch user's highest score from leaderboard
    try:
        leaderboard_response = supabase.table('leaderboard') \
            .select('score') \
            .eq('book_id', book_id) \
            .eq('user_id', user_id) \
            .execute()
        print(f"Leaderboard query response: {leaderboard_response}")
        print(f"Leaderboard query data: {leaderboard_response.data if leaderboard_response else None}")
        print(f"Leaderboard query error: {getattr(leaderboard_response, 'error', None)}")
        if leaderboard_response and hasattr(leaderboard_response, 'data') and leaderboard_response.data and len(leaderboard_response.data) > 0:
            current_highest_score = leaderboard_response.data[0].get('score', 0)
        else:
            print(f"No leaderboard entry found for user_id: {user_id}, book_id: {book_id}")
    except Exception as e:
        print(f"Error fetching leaderboard score: {e}")
        current_highest_score = 0

    # Prepare template data
    template_data = {
        'score': score,
        'book_id': book_id,
        'book_name': book_name,
        'total_questions': total_questions,
        'current_highest_score': current_highest_score
    }
    print(f"Rendering results.html with data: {template_data}")

    return render_template('results.html', **template_data)

@app.route('/global-leaderboard')
@login_required
@supabase_required
def global_leaderboard():
    try:
        global_leaderboard_response = (
            supabase.table('leaderboard')
            .select('username, score, book_id, updated_at, bible_books(name)')
            .order('score', desc=True)
            .order('updated_at', desc=True)
            .limit(20)
            .execute()
        )

        global_leaderboard_data = global_leaderboard_response.data if global_leaderboard_response and hasattr(global_leaderboard_response, 'data') else []
        print(f"Global leaderboard data: {global_leaderboard_data}")

        return render_template('global_leaderboard.html', leaderboard=global_leaderboard_data)

    except Exception as e:
        flash(f"Gagal memuatkan papan pendahulu global: {e}", "error")
        print(f"Error fetching global leaderboard: {e}")
        return redirect(url_for('home'))

@app.route('/my-scores')
@login_required
@supabase_required
def my_scores():
    user_info = session.get('user')
    user_id = user_info['id']

    try:
        response = supabase.table('scores') \
            .select('score, achieved_at, bible_books(name)') \
            .eq('user_id', user_id) \
            .order('achieved_at', desc=True) \
            .execute()
        print(f"My scores response: {response}")
        scores = response.data if response and hasattr(response, 'data') else []
        return render_template('my_scores.html', scores=scores)
    except Exception as e:
        flash(f"Gagal memuatkan skor anda: {e}", "error")
        print(f"Error fetching my scores: {e}")
        return redirect(url_for('home'))

print("\n--- Flask URL Map (Registered Routes) ---")
for rule in app.url_map.iter_rules():
    print(f"Endpoint: {rule.endpoint}, Methods: {rule.methods}, Rule: {rule.rule}")
print("--- End of URL Map ---\n")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)