from sqlalchemy.orm import Session

from app.models import Photo, RecognitionJob
from app.recognition import CloudRecognitionError, combine_fields
from app.storage import photo_path


def run_local(app, job_id):
    with Session(app.state.engine) as session:
        job = session.get(RecognitionJob, job_id)
        job.local_status = "running"
        paths = [photo_path(session.get(Photo, image_id).path) for image_id in job.image_ids]
        session.commit()
    try:
        evidence = [app.state.scan_image(path) for path in paths]
        fields, conflicts = combine_fields(evidence)
        with Session(app.state.engine) as session:
            job = session.get(RecognitionJob, job_id)
            job.local_status, job.fields, job.conflicts, job.evidence = "done", fields, conflicts, evidence
            cloud_enabled = job.cloud_enabled
            session.commit()
        if cloud_enabled:
            app.state.cloud_pool.submit(run_cloud, app, job_id, paths, evidence)
    except Exception:
        with Session(app.state.engine) as session:
            job = session.get(RecognitionJob, job_id)
            job.local_status, job.error = "failed", "本地识别失败，可检查图片后重试或手动填写"
            job.cloud_status = "disabled"
            session.commit()


def run_cloud(app, job_id, paths, evidence):
    with Session(app.state.engine) as session:
        job = session.get(RecognitionJob, job_id)
        job.cloud_status = "running"
        session.commit()
    try:
        fields = app.state.cloud_extract(paths, [e["texts"] for e in evidence])
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
