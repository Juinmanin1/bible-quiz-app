# run_waitress.py 파일 내용
from waitress import serve
from app import app # app.py 파일에서 Flask 인스턴스 'app'을 가져옵니다.

if __name__ == '__main__':
    print("Waitress 서버를 시작합니다...")
    serve(app, host='0.0.0.0', port=5000)