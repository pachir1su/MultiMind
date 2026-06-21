import sys


def main():
    # PySide6 모듈 로드 시도
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print(
            "오류: PySide6를 찾을 수 없습니다.\n"
            "설치 명령어: pip install PySide6",
            file=sys.stderr,
        )
        sys.exit(1)

    # QApplication 생성 (Qt 이벤트 루프)
    app = QApplication(sys.argv)

    # MultiMind 앱 모듈 로드 시도
    try:
        from multimind.app import MultiMindApp
    except ModuleNotFoundError as e:
        QMessageBox.critical(
            None,
            "패키지 오류",
            f"{e}\n\n필요한 패키지를 설치한 뒤 다시 실행해주세요:\n"
            "pip install PySide6 selenium undetected-chromedriver pyperclip",
        )
        sys.exit(1)

    # 메인 윈도우 생성 및 표시
    window = MultiMindApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
