from sqlalchemy.orm import Session

from app.models import Photo, RecognitionJob
from app.recognition import CloudRecognitionError, combine_fields
from app.storage import photo_path
from app.gateway_ocr import GatewayNoTextError, GatewayRecognitionError


def run_local(app, job_id):
    with Session(app.state.engine) as session:
        job = session.get(RecognitionJob, job_id)
        job.local_status = "running"
        paths = [photo_path(session.get(Photo, image_id).path) for image_id in job.image_ids]
        session.commit()
    try:
        evidence, unreadable = [], []
        for index, path in enumerate(paths, start=1):
            try:
                evidence.append(app.state.scan_image(path))
            except GatewayNoTextError:
                unreadable.append(index)
                # Keep one evidence entry per photo for auxiliary recognition.
                evidence.append({'texts': [], 'boxes': []})
        if len(unreadable) == len(paths):
            raise GatewayNoTextError('所有图片都未识别到文字，请换一张文字清晰的照片')
        fields, conflicts = combine_fields(evidence)
        with Session(app.state.engine) as session:
            job = session.get(RecognitionJob, job_id)
            job.local_status, job.fields, job.conflicts, job.evidence = "done", fields, conflicts, evidence
            if unreadable:
                numbers = '、'.join(map(str, unreadable))
                job.error = f'已识别其余图片，第 {numbers} 张未读到文字，请核对'
            cloud_enabled = job.cloud_enabled
            session.commit()
        if cloud_enabled:
            app.state.cloud_pool.submit(run_cloud, app, job_id, paths, evidence)
    except Exception as exc:
        with Session(app.state.engine) as session:
            job = session.get(RecognitionJob, job_id)
            job.local_status = "failed"
            job.error = str(exc) if isinstance(exc, GatewayRecognitionError) else "基础识别失败，可检查图片后重试或手动填写"
            job.cloud_status = "disabled"
            session.commit()


def run_cloud(app, job_id, paths, evidence):
    with Session(app.state.engine) as session:
        job = session.get(RecognitionJob, job_id)
        job.cloud_status = "running"
        thinking_mode = job.cloud_thinking or "disabled"
        session.commit()
    try:
        fields = app.state.cloud_extract(paths, [e["texts"] for e in evidence], thinking_mode)
        with Session(app.state.engine) as session:
            job = session.get(RecognitionJob, job_id)
            job.cloud_fields, job.cloud_status = fields, "done"
            session.commit()
    except Exception as exc:
        with Session(app.state.engine) as session:
            job = session.get(RecognitionJob, job_id)
            job.cloud_status = "failed"
            job.cloud_error = (str(exc) + "；本地结果已保留") if isinstance(exc, CloudRecognitionError) else "云端辅助不可用，本地结果已保留；可稍后重试"
            session.commit()
