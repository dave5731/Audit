import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks, FastAPI

from src.routers.add_router import router



async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(router)


print ("\n\n***********************************************************************")
print ("*****************    CORS enabled for testing *****************")
print ("****************************************************************************\n\n")
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    # read this in from command line argument
   uvicorn.run(app, host="10.0.0.108", port=8510)
