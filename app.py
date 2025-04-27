import os
import random
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from supabase import create_client, Client
from functools import wraps

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
# Use a strong secret key in production
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Initialize Supabase client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Ensure URL and Key are set
supabase = None # Initialize supabase to None
if not url or not key:
    print("SUPABASE_URL or SUPABASE_KEY are not set in the .env file. Supabase features will be unavailable.")
    # In a real app, you might want to stop or show a maintenance page
    # raise ValueError("Supabase URL or Key not set")
else:
    try:
        supabase: Client = create_client(url, key)
        # Optional: Add a small test query here if needed to verify credentials/connection
        # response = supabase.table('bible_books').select('id').limit(1).execute()
        # if response.error:
        #     print(f"Supabase connection test failed: {response.error}")
        #     supabase = None # Set to None if connection fails
        # else:
        #     print("Supabase connection successful.")

    except Exception as e:
        print(f"Failed to create Supabase client: {e}")
        supabase = None # Set to None if client creation fails

# Decorator to ensure Supabase client is available for a route
def supabase_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if supabase is None:
            flash("Aplikasi tidak dapat berhubung dengan pangkalan data (Supabase tidak tersedia). Sila cuba sebentar lagi atau hubungi pentadbir.", "error")
            # Redirect to a page that doesn't require Supabase, like home or a static error page
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


# Jinja2 filter to format datetime objects
def format_datetime_filter(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        return ""
    try:
        # Convert string to datetime object
        if isinstance(value, str):
            # Attempt to parse ISO 8601, including with Z and various offsets
            try:
                 # Handle potential Z suffix and parse
                 dt_object = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                 # Fallback for potentially non-standard formats
                 print(f"Could not parse '{value}' as ISO 8601. Returning original.")
                 return value # Return original value if parsing fails

        elif isinstance(value, datetime):
            dt_object = value
        else:
            # If the value is neither string nor datetime, return it as is
            return value

        # Format the datetime object to the desired string format
        return dt_object.strftime(format)
    except (ValueError, TypeError, AttributeError) as e:
        # Catch errors during formatting (e.g., if dt_object is invalid)
        print(f"Error formatting datetime '{value}': {e}")
        return value # Return original value if formatting fails


app.jinja_env.filters['format_datetime'] = format_datetime_filter

# Decorator to require login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if 'user' is in the Flask session
        if 'user' not in session:
            # Flash a warning message and redirect to login page
            flash("Sila log masuk untuk mengakses halaman ini.", "warning")
            # Store current URL in 'next' param for redirect after login
            return redirect(url_for('login', next=request.url))
        # If user is logged in, proceed to the original route function
        return f(*args, **kwargs)
    return decorated_function

# --- Routes ---

# Home Page
@app.route('/')
def home():
    user = session.get('user')
    username = session.get('username')
    return render_template('home.html', user=user, username=username)

# New User Signup
@app.route('/signup', methods=['GET', 'POST'])
@supabase_required # Ensure Supabase is available
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
            # 1. Check if a profile with this church code and username already exists
            existing_profile = supabase.table('profiles') \
                .select('id', count='exact') \
                .eq('church_code', church_code) \
                .eq('username', username) \
                .execute()

            print(f"Existing profile check: {existing_profile}")

            if existing_profile.count > 0:
                flash("Nama pengguna ini sudah wujud untuk kod gereja ini.", "error")
                return redirect(url_for('signup'))

            # 2. Register the new user in Supabase Auth system
            res = supabase.auth.sign_up({
                "email": email,
                "password": password,
            })

            if not res.user or not res.user.id:
                 flash("Pendaftaran gagal (Supabase Auth). Sila cuba lagi.", "error")
                 print(f"Supabase Auth signup failed: {res.error}")
                 return redirect(url_for('signup'))

            user_id = res.user.id

            # 3. Insert user profile data into the 'profiles' table
            profile_data = {
                'id': str(user_id),
                'church_code': church_code,
                'username': username,
                'email': email,
                'phone': None
            }
            print(f"Inserting profile: {profile_data}")
            supabase.table('profiles').insert(profile_data).execute()

            # 4. Automatically log in the user after successful signup
            # Note: Supabase sign_up now often automatically signs in. This step might be redundant but safe.
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


# User Login
@app.route('/login', methods=['GET', 'POST'])
@supabase_required # Ensure Supabase is available
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
            # 1. Find profile in 'profiles' table using username and church_code to construct email
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

            # 2. Attempt to log in using Supabase Auth with the email and password
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            print(f"Auth response: {res}")

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
                # Menterjemahkan teks Korea: "비밀번호를 잊으셨다면 관리자에게 문의하세요."
                flash("Kata laluan salah. Jika anda terlupa kata laluan, sila hubungi pentadbir.", "error")
                print(f"Supabase Auth signin failed: {res.error}")
                return redirect(url_for('login'))

        except Exception as e:
            error_message = str(e)
            print(f"Login error: {error_message}")
            flash(f"Log masuk gagal: {error_message}", "error")
            return redirect(url_for('login'))

    return render_template('login.html')


# User Logout
@app.route('/logout')
@login_required # Ensure user is logged in to logout
def logout():
    try:
        # Only attempt Supabase sign out if the client was successfully created
        if supabase:
            supabase.auth.sign_out()
            print("Supabase user signed out.")
        else:
             print("Supabase client not available, skipping Supabase sign out.")

    except Exception as e:
        print(f"Error during Supabase sign out: {e}")
        pass

    # Clear the Flask session
    session.clear()
    print("Flask session cleared.")
    flash("Anda telah berjaya log keluar.", "success")
    return redirect(url_for('home'))

# Select Book
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

# Quiz Page
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

        # Security Note: Sending correct_answer to the client is not ideal for security.
        # A more secure approach is to remove 'correct_answer' here and only check on the server in submit_answer.
        # Your submit_answer *does* check on the server, which is good.
        # For consistency with your original code structure, I'll keep it, but be aware.
        # If you want to remove it:
        # for q in questions:
        #    q.pop('correct_answer', None) # Remove correct_answer key


        return render_template('quiz.html',
                               questions=questions,
                               book_id=book_id,
                               total_questions=total_questions,
                               book_name=book_name)
    except Exception as e:
        flash(f"Gagal memuatkan kuiz: {e}", "error")
        print(f"Error loading quiz: {e}")
        return redirect(url_for('select_book'))

# Submit Question Answer
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
        # Fetch the correct answer for the question
        # Ensure this fetch happens *every time* an answer is submitted for security
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


# Complete Quiz
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
        # Save score to 'scores' table
        score_response = supabase.table('scores').insert({
            'user_id': user_id,
            'book_id': book_id,
            'score': final_score,
            'achieved_at': datetime.utcnow().isoformat()
        }).execute()
        print(f"Score insert response: {score_response}")


        # Update leaderboard
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


        # Only upsert if the new score is strictly higher
        if final_score > current_leaderboard_score:
            print(f"New score ({final_score}) is higher than current leaderboard score ({current_leaderboard_score}). Upserting leaderboard...")
            # Ensure you have RLS policies in Supabase that allow a user
            # to INSERT/UPDATE rows in the 'leaderboard' table where user_id = auth.uid()
            leaderboard_response = supabase.table('leaderboard').upsert({
                'book_id': book_id,
                'user_id': user_id,
                'username': username,
                'score': final_score
            }).execute()
            print(f"Leaderboard upsert response: {leaderboard_response}")
            # NOTE: Remember to check RLS policies in Supabase to allow this.

        else:
             print(f"New score ({final_score}) is not higher than current leaderboard score ({current_leaderboard_score}). No leaderboard update needed.")


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
        if "42501" in error_message:
             display_message = "Gagal menyimpan skor tertinggi (isu kebenaran RLS). Sila hubungi pentadbir."
             print("RLS Policy error detected on leaderboard update. Check Supabase RLS settings.")
        else:
             display_message = f'Gagal menyimpan skor: {error_message}'

        return jsonify({'success': False, 'message': display_message}), 500


# Quiz Results Page
@app.route('/results')
@login_required
@supabase_required
def results():
    score = request.args.get('score', type=int)
    book_id = request.args.get('book_id', type=int)
    total_questions = request.args.get('total_questions', type=int)

    book_name = "Kitab Tidak Diketahui"
    current_highest_score = 0

    user_info = session.get('user')
    user_id = user_info['id']

    if book_id is not None:
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

            leaderboard_response = supabase.table('leaderboard') \
                .select('score') \
                .eq('book_id', book_id) \
                .eq('user_id', user_id) \
                .execute()

            if leaderboard_response.data and len(leaderboard_response.data) > 0:
                current_highest_score = leaderboard_response.data[0].get('score', 0)


        except Exception as e:
            print(f"Error fetching book name or user's leaderboard score for results page: {e}")


    if score is None or book_id is None or total_questions is None:
        flash("Maklumat keputusan kuiz tidak lengkap.", "warning")
        return redirect(url_for('select_book'))

    if total_questions == 0:
         flash("Kuiz ini tidak mempunyai soalan yang sah.", "warning")
         return redirect(url_for('select_book'))


    return render_template('results.html',
                           score=score,
                           book_id=book_id,
                           book_name=book_name,
                           total_questions=total_questions,
                           current_highest_score=current_highest_score)

# My Personal Scores Page
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
        scores_data = response.data if response and hasattr(response, 'data') else []

        return render_template('my_scores.html', scores=scores_data)
    except Exception as e:
        flash(f"Gagal memuatkan skor peribadi: {e}", "error")
        print(f"Error fetching personal scores: {e}")
        return redirect(url_for('select_book'))

# Book Leaderboard
@app.route('/leaderboard/<int:book_id>')
@login_required
@supabase_required
def leaderboard(book_id):
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

        leaderboard_response = supabase.table('leaderboard') \
            .select('username, score') \
            .eq('book_id', book_id) \
            .order('score', desc=True) \
            .limit(10) \
            .execute()
        leaderboard_data = leaderboard_response.data if leaderboard_response and hasattr(leaderboard_response, 'data') else []

        return render_template('leaderboard.html',
                               leaderboard=leaderboard_data,
                               book_name=book_name,
                               book_id=book_id)

    except Exception as e:
        flash(f"Gagal memuatkan papan pendahulu kitab: {e}", "error")
        print(f"Error fetching book leaderboard: {e}")
        return redirect(url_for('select_book'))

# --- NEW GLOBAL LEADERBOARD ROUTE ---
# Global Leaderboard
@app.route('/global-leaderboard')
@login_required
@supabase_required
def global_leaderboard():
    try:
        # Fetch top 20 highest scores across all books
        global_leaderboard_response = (
            supabase.table('leaderboard')
            .select('username, score, book_id, bible_books(name)') # Include book name via join
            .order('score', desc=True)
            .limit(20)
            .execute()
        )

        global_leaderboard_data = global_leaderboard_response.data if global_leaderboard_response and hasattr(global_leaderboard_response, 'data') else []

        # Data is formatted by Supabase with 'bible_books(name)', accessible in template

        # Render the global_leaderboard.html template
        return render_template('global_leaderboard.html', leaderboard=global_leaderboard_data)

    except Exception as e:
        flash(f"Gagal memuatkan papan pendahulu global: {e}", "error")
        print(f"Error fetching global leaderboard: {e}")
        return redirect(url_for('home'))


# --- 진단 코드 시작 ---
# Flask 앱 인스턴스가 생성된 후 라우트 맵을 출력하여 등록된 라우트를 확인합니다.
# 이 코드는 app.py 파일이 실행될 때 __name__ == '__main__' 블록 전에 실행됩니다.
print("\n--- Flask URL Map (Registered Routes) ---")
for rule in app.url_map.iter_rules():
    print(f"Endpoint: {rule.endpoint}, Methods: {rule.methods}, Rule: {rule.rule}")
print("--- End of URL Map ---\n")
# --- 진단 코드 끝 ---


# --- Run Application ---
if __name__ == '__main__':
    # Use 0.0.0.0 for accessibility in container/VM, debug=True for development
    # In production, debug must be False and use a production WSGI server
    # Waitress를 사용할 때는 이 app.run() 라인이 실행되지 않습니다.
    app.run(debug=True, host='0.0.0.0', port=5000)