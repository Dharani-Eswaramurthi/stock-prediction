module.exports = {
  apps: [
    {
      name: "backend",
      script: "uvicorn mcp_server:app --host 0.0.0.0 --port 8000",
      interpreter: "python3"
    },
    {
      name: "frontend",
      script: "streamlit run ui_new.py",
      interpreter: "python3",
    }
  ]
}
