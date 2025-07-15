module.exports = {
  apps: [
    {
      name: "backend",
      script: "uvicorn main:app --host 0.0.0.0 --port 8000",
      interpreter: "python3"
    },
    {
      name: "frontend",
      script: "streamlit run frontend_app.py --server.port=8501",
      interpreter: "bash"
    }
  ]
}
