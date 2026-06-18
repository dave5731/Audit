from datetime import datetime
import json
import os
import sys

from typing import Annotated
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from codexTest import page_seo_checker
from src.SEOTest import onePageAnalyzer




PRODUCTION_SERVER = "127.0.0.1"
router = APIRouter(
    prefix="/audit"
    )


@router.post("/performSEOtest")
async def test(
    siteUrl : Annotated[str, Form(min_length=15,max_length=300)],
    background_tasks: BackgroundTasks
):
    try:
        print ("received request")
        pageAnalyizer = onePageAnalyzer.onePageAnalyzer()
        print ("page inited")
        siteUrl="https://nauticalagency.com/"
        pageAnalyizer.analyzePage(siteUrl)
        return True
    except Exception as e:
        print (e)
        return False

@router.post("/performGEOtest")
async def test(
    siteUrl : Annotated[str, Form(min_length=15,max_length=300)],
    background_tasks: BackgroundTasks
):
    try:
        
        return True
    except Exception as e:
        return False


@router.post("/pageSEOChecker")
async def pageSEOChecker(
    siteUrl: Annotated[str, Form(min_length=4, max_length=300)],
    timeout: Annotated[int, Query(ge=1, le=60)] = page_seo_checker.REQUEST_TIMEOUT
):
    try:
        return await run_in_threadpool(page_seo_checker.run_audit, siteUrl, timeout)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}
