"""药物研发智能体的配置模块。"""
import os
import json

# 路径配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_PDB = os.path.join(DATA_DIR, "target.pdb")
RECEPTOR_PDBQT = os.path.join(DATA_DIR, "receptor.pdbqt")

# ==========================================
# 大语言模型配置（支持任意 OpenAI 兼容接口）
# ==========================================
# 通用配置方式：通过环境变量指定 LLM_BASE_URL、LLM_API_KEY、LLM_MODEL
# 不配置时，默认尝试从 Kimi CLI 凭据自动读取

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.kimi.com/coding/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "kimi-k2.6")


def _get_api_key():
    """按优先级获取 API Key。

    优先级:
        1. 环境变量 LLM_API_KEY
        2. 环境变量 KIMI_API_KEY（兼容旧配置）
        3. Kimi CLI OAuth 凭据文件（~/.kimi/credentials/kimi-code.json）
    """
    # 环境变量优先
    env_key = os.getenv("LLM_API_KEY", "") or os.getenv("KIMI_API_KEY", "")
    if env_key:
        return env_key

    # 尝试读取 Kimi CLI 的 OAuth Token
    cred_path = os.path.expanduser("~/.kimi/credentials/kimi-code.json")
    if os.path.exists(cred_path):
        try:
            with open(cred_path) as f:
                data = json.load(f)
                return data.get("access_token", "")
        except Exception:
            pass
    return ""


LLM_API_KEY = _get_api_key()

# ==========================================
# 分子对接配置
# ==========================================
DOCKING_CENTER = [18.5, -2.0, 22.0]  # 优化后的活性位点中心（空洞分析+AB测试验证）
DOCKING_SIZE = [30.0, 30.0, 30.0]      # 搜索盒子大小（埃）
DOCKING_EXHAUSTIVENESS = 8

# 对接中心优化记录 (H008):
#   旧值: [18.28, 2.31, 21.44] — 蛋白质整体质心，偏向口袋上方
#   新值: [18.5, -2.0, 22.0] — 空洞密度分析最优 + AB测试验证
#   依据: 空洞检测(2Å网格)发现Y=-2~-3Å处蛋白质密度最低且被充分包围，
#         AB测试(cavity_v2 vs current) avg BE改善 0.035~0.047 kcal/mol
#   注意: 改善幅度有限(~0.04 kcal/mol)，说明30Å盒子足以覆盖活性位点，
#         中心偏移对大盒子影响不大。真正需要的是更好的分子设计。

# ==========================================
# 分子生成配置
# ==========================================
N_GENERATED_MOLECULES = 50
N_TOP_MOLECULES = 10

# ==========================================
# 类药性质过滤参数
# ==========================================
MAX_MW = 500
MIN_MW = 150
MAX_LOGP = 5.0
MIN_LOGP = -0.5
MAX_TPSA = 140
MIN_QED = 0.3

# ==========================================
# 合成规划配置
# ==========================================
