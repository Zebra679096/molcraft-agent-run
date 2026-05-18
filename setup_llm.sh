#!/bin/bash
# LLM API 配置脚本
# 用法: source setup_llm.sh
#
# 请选择以下方式之一配置：

# ============================================
# 方式一：Kimi API Key（推荐，kimi-k2.6 模型最快）
# 获取地址: https://platform.moonshot.cn
# ============================================
# export LLM_API_KEY="sk-your-kimi-api-key"
# export LLM_BASE_URL="https://api.moonshot.cn/v1"
# export LLM_MODEL="kimi-k2.6"

# ============================================
# 方式二：DeepSeek API Key（更便宜，兼容 OpenAI 格式）
# 获取地址: https://platform.deepseek.com
# ============================================
# export LLM_API_KEY="sk-your-deepseek-api-key"
# export LLM_BASE_URL="https://api.deepseek.com"
# export LLM_MODEL="deepseek-chat"

# ============================================
# 方式三：Kimi OAuth 登录（免费额度）
# 运行: kimi login
# 然后在浏览器访问提示的URL，输入设备码
# ============================================

echo "请取消注释并填写上方的 API Key 配置"
echo "配置完成后，运行: python main.py --iterations 1"
