import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

def get_video_duration(video_path: str) -> float:
    """Retorna a duração do vídeo em segundos usando ffprobe."""
    if not os.path.exists(video_path):
        return 0.0
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=10)
        return float(res.stdout.strip())
    except Exception as e:
        logger.error(f"Erro ao obter duração do vídeo {video_path}: {e}")
        return 0.0

def adjust_video_duration_for_pipeline(input_path: str, output_path: str, target_max_seconds: float = 165.0) -> tuple[str, str]:
    """
    Ajusta a duração do vídeo conforme a regra:
    - Se a duração for <= 165s (2:45 min): mantém como está.
    - Se a duração for > 165s e <= 240s (4 min): acelera proporcionalmente para durar exatamente 165s.
    - Se a duração for > 240s (> 4 min): CORTA nos primeiros 4 minutos (240s) e ACELERA esses 4 min inteiros para durar exatamente 165s (2:45 min).
    """
    if not os.path.exists(input_path):
        logger.error(f"Arquivo não encontrado: {input_path}")
        return input_path, "error"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = get_video_duration(input_path)
    logger.info(f"Analisando duração do vídeo {os.path.basename(input_path)}: {duration:.2f}s")

    if duration > 240.0:
        logger.info(f"✂️ Vídeo de {duration:.2f}s excede 4 minutos (>240s). Aplicando pipeline: cortar 4 min → acelerar para 2:45 min...")
        tmp_cut_path = output_path.replace(".mp4", "_cut4min.mp4")
        os.makedirs(os.path.dirname(tmp_cut_path), exist_ok=True)
        
        cut_ok = truncate_video(input_path, tmp_cut_path, seconds=240.0)
        if not cut_ok or not os.path.exists(tmp_cut_path):
            logger.error("Falha ao cortar os primeiros 4 min. Tentando aceleração direta...")
            speed_factor = duration / target_max_seconds
            speed_ok = speedup_video(input_path, output_path, speed_factor)
            if speed_ok and os.path.exists(output_path):
                return output_path, "adjusted"
            return input_path, "error"

        speed_factor = 240.0 / target_max_seconds
        logger.info(f"Acelerando 4 min cortado em {speed_factor:.4f}x para encaixar em {target_max_seconds}s (2:45 min)...")
        speed_ok = speedup_video(tmp_cut_path, output_path, speed_factor)
        try: os.remove(tmp_cut_path)
        except Exception: pass

        if speed_ok and os.path.exists(output_path):
            return output_path, "truncated"
        logger.error("Falha ao acelerar o corte. Usando original como fallback.")
        return input_path, "error"

    if duration > target_max_seconds:
        speed_factor = duration / target_max_seconds
        logger.info(f"Vídeo de {duration:.2f}s está acima de {target_max_seconds}s. Acelerando por fator {speed_factor:.3f}x para 165s...")
        success = speedup_video(input_path, output_path, speed_factor)
        if success and os.path.exists(output_path):
            return output_path, "adjusted"

    return input_path, "ready"

def speedup_video(input_path: str, output_path: str, speed_factor: float) -> bool:
    """Acelera vídeo e áudio via ffmpeg (setpts + atempo)."""
    if not os.path.exists(input_path):
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pts_factor = 1.0 / speed_factor
    if speed_factor <= 2.0:
        af_filter = f"atempo={speed_factor:.4f}"
    else:
        af_filter = f"atempo=2.0,atempo={speed_factor/2.0:.4f}"

    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-filter_complex', f"[0:v]setpts={pts_factor:.4f}*PTS[v];[0:a]{af_filter}[a]",
        '-map', '[v]', '-map', '[a]',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac',
        output_path
    ]
    try:
        logger.info(f"Acelerando vídeo {input_path} em {speed_factor:.3f}x para {output_path}...")
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Erro ao acelerar vídeo com ffmpeg: {e}")
        return False

def truncate_video(input_path: str, output_path: str, seconds: float = 165.0) -> bool:
    """Corta o vídeo nos primeiros N segundos."""
    if not os.path.exists(input_path):
        logger.error(f"Arquivo de entrada não encontrado para corte: {input_path}")
        return False
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        'ffmpeg', '-y', '-ss', '0', '-i', input_path, '-t', str(seconds),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', output_path
    ]
    try:
        logger.info(f"Cortando vídeo {input_path} para {seconds}s...")
        subprocess.run(cmd, capture_output=True, check=True, timeout=300)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Erro ao cortar vídeo com ffmpeg: {e}")
        return False

def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extrai a faixa de áudio de um vídeo e a converte para MP3 usando ffmpeg."""
    if not os.path.exists(video_path):
        return False
    os.makedirs(os.path.dirname(audio_path), exist_ok=True)
    cmd = ['ffmpeg', '-y', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-q:a', '2', audio_path]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
    except Exception as e:
        logger.error(f"Erro ao extrair áudio: {e}")
        return False
