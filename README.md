# Rice Trade Intelligence Dashboard (Streamlit)

## 실행 방법 (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## 구성

- `app.py`: Streamlit UI (대시보드 / 쌀 오퍼 등록 / 해상 운임 등록)
- `db.py`: SQLite 연결/스키마/INSERT
- `rice_trade_intel.db`: 실행 후 자동 생성되는 SQLite DB 파일
- `PRD_Rice_Trade_Intelligence_Dashboard.txt`: 전달받은 PRD 원문

