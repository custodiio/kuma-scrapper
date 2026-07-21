import os
import json
import subprocess
import logging

logger = logging.getLogger(__name__)

def get_video_duration(video_path: str) -> float:
    """Retorna a duração do vídeo em segundos usando ffprobe."""
    if not os.path.exists(video_path):
        logger.error(f"Arquivo de vídeo não encontrado para ffprobe: {video_path}")
        return 0.0
    
    cmd = [
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Tenta extrair a duração dos metadados do formato geral
        duration = data.get('format', {}).get('duration')
        if duration:
            return float(duration)
            
        # Fallback: Tenta extrair dos metadados do stream de vídeo
        for stream in data.get('streams', []):
            duration = stream.get('duration')
            if duration:
                return float(duration)
                
        return 0.0
    except Exception as e:
        logger.error(f"Erro ao obter duração do vídeo via ffprobe: {e}")
        return 0.0

def adjust_video_duration_for_pipeline(input_path: str, output_path: str, target_max_seconds: float = 165.0) -> tuple[str, str]:
    """
    Ajusta a duração do vídeo alterando a VELOCIDADE (speedup) para caber em 2:45 min (165s max) SEM CORTAR o vídeo.
    - Se a duração for <= 165s: mantém o vídeo como está.
    - Se a duração for > 165s e <= 240s (4 min): acelera o vídeo e áudio via ffmpeg (setpts + atempo) para durar exatamente 165s.
    - Se a duração for > 240s (> 4 min): retorna status 'opaque_over_5min' (Requer Ação).
    """
    if not os.path.exists(input_path):
        logger.error(f"Arquivo não encontrado: {input_path}")
        return input_path, "error"

    duration = get_video_duration(input_path)
    logger.info(f"Analisando duração do vídeo {os.path.basename(input_path)}: {duration:.2f}s")

    if duration > 240.0:
        logger.warning(f"⚠️ Vídeo de {duration:.2f}s excede 4 minutos (>240s). Requer ação do usuário (Dividir / Descartar).")
        return input_path, "opaque_over_5min"

    if duration > target_max_seconds:
        speed_factor = duration / target_max_seconds
        logger.info(f"Vídeo de {duration:.2f}s está acima de {target_max_seconds}s. Acelerando velocidade por fator {speed_factor:.3f}x para encaixar em 165s...")
        success = speedup_video(input_path, output_path, speed_factor)
        if success and os.path.exists(output_path):
            return output_path, "adjusted"

    return input_path, "ready"

def speedup_video(input_path: str, output_path: str, speed_factor: float) -> bool:
    """Acelera a velocidade do vídeo e do áudio proporcionalmente com ffmpeg (setpts + atempo) sem cortar o final."""
    if not os.path.exists(input_path) or speed_factor <= 1.0:
        return False

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
        subprocess.run(cmd, capture_output=True, check=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Erro ao acelerar vídeo com ffmpeg: {e}")
        return False

def truncate_video(input_path: str, output_path: str, seconds: float = 165.0) -> bool:
    """Corta o vídeo para uma duração máxima em segundos de forma ultrarrápida (sem re-codificar)."""
    if not os.path.exists(input_path):
        logger.error(f"Arquivo de entrada não encontrado para corte: {input_path}")
        return False
        
    cmd = [
        'ffmpeg', '-y', '-i', input_path, '-t', str(seconds),
        '-c:v', 'copy', '-c:a', 'copy', output_path
    ]
    try:
        logger.info(f"Cortando vídeo {input_path} para {seconds}s...")
        subprocess.run(cmd, capture_output=True, check=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        logger.error(f"Erro ao cortar vídeo com ffmpeg: {e}")
        return False

def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extrai a faixa de áudio de um vídeo e a converte para MP3 usando ffmpeg."""
    if not os.path.exists(video_path):
        logger.error(f"Arquivo de vídeo não encontrado para extração de áudio: {video_path}")
        return False
        
    cmd = [
        'ffmpeg', '-y', '-i', video_path, '-vn',
        '-acodec', 'libmp3lame', '-q:a', '2', audio_path
    ]
    try:
        logger.info(f"Extraindo áudio do vídeo {video_path} para {audio_path}...")
        subprocess.run(cmd, capture_output=True, check=True)
        return os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
    except Exception as e:
        logger.error(f"Erro ao extrair áudio com ffmpeg: {e}")
        return False

def process_media_for_pipeline(video_path: str, output_dir: str, category: str) -> tuple[str, str, bool]:
    """
    Processa a mídia baixada.
    Se a categoria for 'shorts' e o vídeo tiver mais de 3 minutos (180s), trunca para 2.55 minutos (175s).
    Extrai o áudio em MP3.
    Retorna (caminho_video_final, caminho_audio_final, sucesso)
    """
    os.makedirs(output_dir, exist_ok=True)
    video_basename = os.path.basename(video_path)
    name_without_ext, _ = os.path.splitext(video_basename)
    
    final_video_path = os.path.join(output_dir, f"{name_without_ext}_processed.mp4")
    final_audio_path = os.path.join(output_dir, f"{name_without_ext}_audio.mp3")
    
    try:
        duration = get_video_duration(video_path)
        logger.info(f"Vídeo {video_basename} tem duração de {duration:.2f}s (Categoria: {category})")
        
        # Lógica de truncamento para Shorts: se for short e a duração for > 180s (3 minutos)
        should_truncate = (category.lower() == 'shorts' and duration > 180.0)
        
        if should_truncate:
            logger.info(f"Vídeo é Short e tem {duration:.2f}s (> 180s). Truncando para 2.55 min (175s)...")
            video_success = truncate_video(video_path, final_video_path, seconds=175.0)
            if not video_success:
                logger.error("Falha ao truncar vídeo. Usando vídeo original como fallback.")
                final_video_path = video_path
        else:
            logger.info("Nenhum truncamento necessário para este vídeo.")
            final_video_path = video_path
            
        # Extrai o áudio do vídeo final (truncado ou original)
        audio_success = extract_audio(final_video_path, final_audio_path)
        if not audio_success:
            logger.error("Falha ao extrair áudio.")
            return final_video_path, "", False
            
        return final_video_path, final_audio_path, True
        
    except Exception as e:
        logger.error(f"Erro geral no processamento de mídia: {e}")
        return video_path, "", False
