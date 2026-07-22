import sys, re

NEW_COOKIE = "device_web_cpu_core=4; device_web_memory_size=8; architecture=amd64; enter_pc_once=1; UIFID_TEMP=9909fc4602c90e11cbb1ca2fa8411678673d4386b8d7ca05c125f9fb0905826b59e8846fd7eced208d65694747e26d892db80b4834a7c32161f59a78d52cdd9cc1d7c5a4cdee966d673e2c35a1a102cd; x-web-secsdk-uid=5e0d7d9b-94c0-4207-909d-221b6ee15abd; s_v_web_id=verify_mrs21irw_gHQm5k4L_yj6G_4d77_BpMP_ZEdgFmhyDIv7; is_support_rtm_web_ts=1; hevc_supported=true; dy_swidth=1366; dy_sheight=768; is_dash_user=1; fpk1=U2FsdGVkX1/StII5wcuU631L0xcbhny3DHZbJYkkFersfvC1QfgjMoeZy5RSSWV+hBEQHqYUneQOfck8oZRMTQ==; fpk2=73c2e21c0fc47f8841aa6000af1e64c7; passport_csrf_token=d1773c6eff6b9acdb530fe63bba2f9dd; passport_csrf_token_default=d1773c6eff6b9acdb530fe63bba2f9dd; __security_mc_1_s_sdk_crypt_sdk=e629236d-4193-ab75; bd_ticket_guard_client_web_domain=2; UIFID=9909fc4602c90e11cbb1ca2fa8411678673d4386b8d7ca05c125f9fb0905826b556baf929610e08e21fe2dcded6768f0e42e1e2c2582f7c01fdc08159ead5761efbf1bef8e8bbffcf2de2e7e6f6724e8d7737a029d532fcd5bfa3580cc93ddd47054bda523e830a55a47f2b37a2dd45af2b0466230e9b034f6d7a362861fadaaac5f4aa60a331e865d410bc9847a68efe993c300bf6644e3b1df29e17a1a25ce; download_guide=%223%2F20260719%2F0%22; volume_info=%7B%22isUserMute%22%3Afalse%2C%22isMute%22%3Atrue%2C%22volume%22%3A0.5%7D; __ac_nonce=06a5ff153001899cf4ea8; __ac_signature=_02B4Z6wo00f01VqGdsQAAIDBOJhygcgUamlapnJAAD0C73; stream_recommend_feed_params=%22%7B%5C%22cookie_enabled%5C%22%3Atrue%2C%5C%22screen_width%5C%22%3A1366%2C%5C%22screen_height%5C%22%3A768%2C%5C%22browser_online%5C%22%3Atrue%2C%5C%22cpu_core_num%5C%22%3A4%2C%5C%22device_memory%5C%22%3A8%2C%5C%22downlink%5C%22%3A1.3%2C%5C%22effective_type%5C%22%3A%5C%224g%5C%22%2C%5C%22round_trip_time%5C%22%3A150%7D%22; home_can_add_dy_2_desktop=%221%22; strategyABtestKey=%221784672618.149%22; bd_ticket_guard_client_data=eyJiZC10aWNrZXQtZ3VhcmQtdmVyc2lvbiI6MiwiYmQtdGlja2V0LWd1YXJkLWl0ZXJhdGlvbi12ZXJzaW9uIjoxLCJiZC10aWNrZXQtZ3VhcmQtcmVlLXB1YmxpYy1rZXkiOiJCTFovVlRDb1hEQjdKOU5sdk9SUkZIeXFZODhHWnk2SXpiVTdNYStIOFExbUlNc1p5UUxYNzg5VDNZd2xRbGQ4ZUJwUjZKMm9xYlNlMFFUbTN5ZGxpRTg9IiwiYmQtdGlja2V0LWd1YXJkLXdlYi12ZXJzaW9uIjoyfQ==; biz_trace_id=3a8e33e3; bd_ticket_guard_client_data_v2=eyJyZWVfcHVibGljX2tleSI6IkJMWi9WVENvWERCN0o5Tmx2T1JSRkh5cVk4OEdaeTZJemJVN01hK0g4UTFtSU1zWnlRTFg3ODlUM1l3bFFsZDhlQnBSNkoyb3FiU2UwUVRtM3lkbGlFOD0iLCJyZXFfY29udGVudCI6InNlY190cyIsInJlcV9zaWduIjoid2ZOenJCY2ljMEcxSFdubXVHeEhGLzRMK3NXU3lxdWtDZWdwSll4aGdCST0iLCJzZWNfdHMiOiIjK0J0SlNWK3pCdENRbjhWb3FGMThEcUJHVVV4RkFETmxaZkg5VFdyZDV3am9mMjQ4NFhUVHNZU0RrdWx4In0=; gulu_source_res=eyJwX2luIjoiYzlmNjlhZGMzOGFmYjIyYTFiNTlkM2JlYTY1MzllMWIwZWRhOGE0YzMxYzNiY2U3NWU5MGNiMjdjYmIwMTgwZCJ9; IsDouyinActive=true; sdk_source_info=7e276470716a68645a606960273f276364697660272927676c715a6d6069756077273f276364697660272927666d776a68605a607d71606b766c6a6b5a7666776c7571273f275e58272927666a6b766a69605a696c6061273f27636469766027292762696a6764695a7364776c6467696076273f275e582729277672715a646971273f2763646976602729277f6b5a666475273f2763646976602729276d6a6e5a6b6a716c273f2763646976602729276c6b6f5a7f6367273f27636469766027292771273f273c34333d3434363233313d3234272927676c715a75776a716a666a69273f2763646976602778; bit_env=O4uiipGBasD6Zv2QV3mIvbPdNJXRYzPZ-LKxj0NJRlxlZ3B-Oj0x_M6hfWY5NBh2c2qmuYQj-7U9cWwZNZw4AND5CjUwb9ZfomKGd8nfJRiwhDwIM3LFcElRMGwcu5P9vgVZiPnSeMDQV_Jrt13zlFBceJPEW_vpzervGN7DMwx8emyaocyMbdS7Tp3ylbfMiwTD90UwTpERSqNxCTQ1DQxlOJz23W7iVc_VwF4ceacNVIIGztA_JXxSy8Kr5K5-3axQ2mPPvsRs2cSjPQyFz87X5uRjG9z-8P_hsIUbbkxuhCxRxRcShlQq80SMAJRTJxUzC9EwVgnM8yaV_sGu-XnAlCiqMsgpKUS09E_UB50MEwG9yDqmdJoePKgbFDUmaAI0gYgJOBppHILkOP3fFb3RPjpSNhVYJeI-hGrj9MtbUjn5K-U192ttOxTRy2Q9j0zqAk1CGAgOa52hgilQG02BHb1DeRGMIyiFY8au19KV2n7nAajWtoknFMGEE0ibmHwH8qozdKHeSkvvqIdv8qU_h-47VtVrH1O1SaTkS1s=; passport_auth_mix_state=mnmnhve3pensd5tvqx064hd8cdm9b4a0vcbi6q6rvx8qel64"

CONFIG_PATH = "/app/scrapper_douyin/douyin_api/crawlers/douyin/web/config.yaml"

# Lê o arquivo como texto puro para não quebrar o YAML
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# Substitui o valor do Cookie com regex
# O cookie fica em várias linhas potencialmente, então encontramos a chave e substituímos até o próximo campo
new_cookie_line = f"      Cookie: {NEW_COOKIE}"
content = re.sub(r"      Cookie:.*", new_cookie_line, content, flags=re.DOTALL, count=1)

# Se tiver continuation lines (cookie quebrado em múltiplas linhas com espaço), limpa
# Usa abordagem segura: substitui de "Cookie:" até próxima chave no mesmo nível
content = re.sub(
    r"(      Cookie: )(.+?)(\n      [A-Za-z])",
    lambda m: f"{m.group(1)}{NEW_COOKIE}{m.group(3)}",
    content,
    flags=re.DOTALL
)

with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("✅ Cookie atualizado em crawlers/douyin/web/config.yaml!")

# Verifica os primeiros chars do cookie salvo
with open(CONFIG_PATH, "r") as f:
    for line in f:
        if "Cookie:" in line:
            print(f"  Cookie salvo: {line.strip()[:80]}...")
            break

# Testa download
import httpx
DOUYIN_API_BASE = "http://localhost:5555"
video_url = "https://www.douyin.com/video/7661112899154300196"
print(f"\nTestando download: {video_url}")
try:
    with httpx.Client(timeout=60.0) as client:
        with client.stream("GET", f"{DOUYIN_API_BASE}/api/download", params={"url": video_url, "with_watermark": "false"}) as r:
            ct = r.headers.get("Content-Type", "")
            print(f"Status: {r.status_code} | Content-Type: {ct}")
            if r.status_code == 200 and "application/json" not in ct:
                total = sum(len(c) for c in r.iter_bytes(16384))
                print(f"✅ Download OK! {total:,} bytes")
            else:
                print(f"❌ Erro: {r.read()[:300]}")
except Exception as e:
    print(f"❌ Exceção: {e}")
