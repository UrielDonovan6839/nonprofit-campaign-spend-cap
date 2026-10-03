import uvicorn

from nonprofit_service import create_app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("run_campaign:app", host="127.0.0.1", port=8000, reload=False)
