from fastapi import FastAPI

app = FastAPI(title="SLA Intelligent Diagnosis API")


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    return {"status": "ready"}
