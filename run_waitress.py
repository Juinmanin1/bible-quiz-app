# run_waitress.py 파일 내용
from waitress import serve
from app import app # app.py 파일에서 Flask 인스턴스 'app'을 가져옵니다.

if __name__ == '__main__':
    print("Waitress 서버를 시작합니다...")
    # host와 port는 app.run()에서 사용하던 것과 동일하게 설정합니다.
    # Waitress는 기본적으로 디버그 모드나 자동 재시작 기능을 포함하지 않습니다.
    serve(app, host='0.0.0.0', port=5000)