#!/usr/bin/env python
"""
50 条跨行业 RAG 真实链路评测脚本。

覆盖链路：
- DashScope Embedding
- Milvus 向量写入/检索
- Elasticsearch BM25 写入/检索
- 轻量图谱检索
- Rerank 重排

脚本会生成唯一 run_id，使用独立 Milvus collection type，避免历史数据干扰向量召回。
"""

import asyncio
import argparse
from contextlib import suppress
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config
from app.models.schemas import SearchRequest
from app.services.cache_service import get_cache_service
from app.services.embedding_service import EmbeddingService
from app.services.es_service import get_es_service
from app.services.graph_retrieval_service import get_graph_retrieval_service
from app.services.milvus_service import MilvusService
from app.services.rag_evaluation_service import get_rag_evaluation_service
from app.services.rag_search_pipeline_service import run_search_pipeline_with_profile

DEFAULT_INDUSTRY50_SEED = 20260602
REPORT_KIND_INDUSTRY50 = "industry50"
REPORTS_DIR = PROJECT_ROOT / "reports" / "rag_eval"
LAST_REPORT_PATH = PROJECT_ROOT / "data" / "rag_eval_industry50_last.json"
STAGE_LATENCY_KEYS = {
    "embedding_latency_ms": "embedding",
    "es_latency_ms": "es_bm25",
    "milvus_latency_ms": "vector_search",
    "graph_latency_ms": "graph_search",
    "rerank_latency_ms": "rerank",
}


DOCS: List[Dict[str, Any]] = [
    {
        "industry": "金融",
        "slug": "fin_credit_risk",
        "title": "小微企业授信风控",
        "description": "小微企业授信风控模型，融合纳税流水、发票、司法风险和经营异常数据，输出准入策略、额度建议和预警名单。",
        "query": "需要识别小微企业贷款申请里的发票异常、司法风险并给出授信额度，应该找哪个能力？",
        "keywords": ["授信", "发票", "司法风险", "额度"],
    },
    {
        "industry": "金融",
        "slug": "fin_aml",
        "title": "反洗钱交易监测",
        "description": "反洗钱交易监测规则引擎，识别频繁拆分转账、异常收付款网络和高风险客户资金流向。",
        "query": "银行想监控拆分转账和异常收付款网络来做反洗钱预警，匹配哪个方案？",
        "keywords": ["反洗钱", "拆分转账", "资金流向"],
    },
    {
        "industry": "金融",
        "slug": "fin_claim",
        "title": "保险智能理赔",
        "description": "保险智能理赔审核，结合保单责任、医疗票据、事故材料和历史赔付记录完成自动核赔。",
        "query": "车险和医疗险材料进入系统后要自动核赔并校验票据责任，应该召回什么能力？",
        "keywords": ["保险", "理赔", "票据", "核赔"],
    },
    {
        "industry": "金融",
        "slug": "fin_portfolio",
        "title": "投资组合风险归因",
        "description": "投资组合风险归因分析，按行业、因子、久期和波动率拆解收益来源与风险暴露。",
        "query": "资管团队要看组合收益来自哪些行业和因子，同时评估波动率暴露，用哪条数据？",
        "keywords": ["投资组合", "风险归因", "因子", "波动率"],
    },
    {
        "industry": "金融",
        "slug": "fin_payment",
        "title": "支付清结算对账",
        "description": "支付清结算对账系统，对接渠道流水、商户订单和银行回单，定位长短款与挂账原因。",
        "query": "第三方支付平台要核对商户订单、银行回单并查长短款，应该命中哪个文档？",
        "keywords": ["支付", "清结算", "对账", "长短款"],
    },
    {
        "industry": "医疗",
        "slug": "med_image",
        "title": "肺部影像辅助诊断",
        "description": "肺部影像辅助诊断模型，分析 CT 结节、磨玻璃影和随访变化，辅助医生生成结构化报告。",
        "query": "医院要分析肺部 CT 的结节和磨玻璃影变化并生成结构化报告，找哪个能力？",
        "keywords": ["肺部CT", "结节", "结构化报告"],
    },
    {
        "industry": "医疗",
        "slug": "med_emr",
        "title": "电子病历质控",
        "description": "电子病历质控系统，检查主诉、诊断、医嘱、病程记录一致性，发现缺项和书写风险。",
        "query": "病案室希望检查主诉诊断医嘱是否一致，还要发现病历缺项，应该召回哪条？",
        "keywords": ["电子病历", "质控", "医嘱", "缺项"],
    },
    {
        "industry": "医疗",
        "slug": "med_triage",
        "title": "急诊分诊辅助",
        "description": "急诊分诊辅助，根据症状、生命体征、过敏史和危急值提示分诊级别与绿色通道建议。",
        "query": "急诊入口要根据生命体征和危急值判断分诊等级，还要提示绿色通道，用哪个方案？",
        "keywords": ["急诊", "分诊", "生命体征", "危急值"],
    },
    {
        "industry": "医疗",
        "slug": "med_drug",
        "title": "药品相互作用审方",
        "description": "药品相互作用审方能力，识别重复用药、禁忌组合、剂量异常和特殊人群用药风险。",
        "query": "处方系统需要发现重复用药、禁忌组合以及老人儿童剂量异常，应该匹配哪项？",
        "keywords": ["审方", "禁忌", "剂量", "重复用药"],
    },
    {
        "industry": "医疗",
        "slug": "med_followup",
        "title": "慢病随访管理",
        "description": "慢病随访管理平台，跟踪血糖、血压、用药依从性和复诊计划，生成干预任务。",
        "query": "社区医院要跟踪糖尿病高血压患者指标和用药依从性，并自动生成随访任务，找哪个？",
        "keywords": ["慢病", "血糖", "血压", "随访"],
    },
    {
        "industry": "制造",
        "slug": "mfg_quality",
        "title": "机器视觉质检",
        "description": "机器视觉质检系统，检测产线外观划痕、尺寸偏差、漏装和装配缺陷，支持缺陷追溯。",
        "query": "工厂产线要检测划痕、尺寸偏差和漏装，还要做缺陷追溯，应该召回哪个能力？",
        "keywords": ["机器视觉", "质检", "划痕", "漏装"],
    },
    {
        "industry": "制造",
        "slug": "mfg_mes",
        "title": "MES 工单排产",
        "description": "MES 工单排产模块，管理生产订单、工艺路线、设备产能、换线时间和在制品进度。",
        "query": "制造车间要根据设备产能、工艺路线和换线时间安排生产工单，匹配哪条数据？",
        "keywords": ["MES", "工单", "排产", "换线"],
    },
    {
        "industry": "制造",
        "slug": "mfg_maintenance",
        "title": "设备预测性维护",
        "description": "设备预测性维护模型，分析振动、温度、电流和故障工单，预测轴承、刀具和电机异常。",
        "query": "想通过振动温度电流预测轴承或电机快坏了，用哪个维护能力？",
        "keywords": ["预测性维护", "振动", "轴承", "电机"],
    },
    {
        "industry": "制造",
        "slug": "mfg_plc",
        "title": "PLC 产线控制",
        "description": "PLC 产线控制方案，支持西门子 S7、梯形图逻辑、传感器联锁和安全停机策略。",
        "query": "自动化产线需要西门子 S7 梯形图、传感器联锁和安全停机，应该找哪个文档？",
        "keywords": ["PLC", "西门子S7", "梯形图", "联锁"],
    },
    {
        "industry": "制造",
        "slug": "mfg_supply",
        "title": "供应链缺料预警",
        "description": "供应链缺料预警，结合 BOM、采购周期、库存水位和供应商交付风险，预测停线风险。",
        "query": "计划员希望根据 BOM、库存和供应商交付风险提前发现停线缺料，应该命中哪项？",
        "keywords": ["BOM", "缺料", "供应商", "停线"],
    },
    {
        "industry": "零售",
        "slug": "ret_recommend",
        "title": "电商个性化推荐",
        "description": "电商个性化推荐系统，融合浏览、加购、购买、价格偏好和相似商品，生成首页与详情页推荐。",
        "query": "商城要根据浏览加购购买和价格偏好做首页商品推荐，应该找哪个方案？",
        "keywords": ["电商", "推荐", "加购", "价格偏好"],
    },
    {
        "industry": "零售",
        "slug": "ret_inventory",
        "title": "门店动态补货",
        "description": "门店动态补货模型，结合销量预测、库存周转、缺货率、促销计划和天气因素生成补货建议。",
        "query": "连锁门店想结合天气、促销和库存周转来自动给补货建议，召回哪条？",
        "keywords": ["门店", "补货", "促销", "库存周转"],
    },
    {
        "industry": "零售",
        "slug": "ret_member",
        "title": "会员流失预警",
        "description": "会员流失预警，分析 RFM、消费频次、客单价、券使用和沉默周期，触达高风险会员。",
        "query": "运营要根据 RFM、客单价和沉默周期判断哪些会员可能流失，用哪个能力？",
        "keywords": ["会员", "流失", "RFM", "沉默周期"],
    },
    {
        "industry": "零售",
        "slug": "ret_price",
        "title": "竞品价格监控",
        "description": "竞品价格监控平台，抓取渠道价格、优惠券、库存状态和活动节奏，支持调价建议。",
        "query": "商品经理想抓取竞品渠道价格、优惠券和库存状态来辅助调价，应该匹配哪个？",
        "keywords": ["竞品", "价格监控", "优惠券", "调价"],
    },
    {
        "industry": "零售",
        "slug": "ret_search",
        "title": "商品搜索排序",
        "description": "商品搜索排序能力，融合关键词相关性、类目、销量、库存、转化率和个性化偏好。",
        "query": "站内搜索需要同时考虑关键词相关性、销量库存和用户偏好，召回哪条？",
        "keywords": ["商品搜索", "排序", "转化率", "库存"],
    },
    {
        "industry": "物流",
        "slug": "log_route",
        "title": "同城配送路径优化",
        "description": "同城配送路径优化，考虑订单时窗、骑手位置、道路拥堵、装载量和超时赔付风险。",
        "query": "配送平台要考虑订单时窗、骑手位置和拥堵情况来减少超时赔付，应该命中哪个？",
        "keywords": ["同城配送", "路径优化", "时窗", "拥堵"],
    },
    {
        "industry": "物流",
        "slug": "log_cold_chain",
        "title": "冷链温湿度监控",
        "description": "冷链温湿度监控系统，采集车厢传感器、开门记录、轨迹和告警，保障药品生鲜运输。",
        "query": "运输药品和生鲜时要监控车厢温湿度、开门记录和轨迹告警，找哪个方案？",
        "keywords": ["冷链", "温湿度", "开门记录", "轨迹"],
    },
    {
        "industry": "物流",
        "slug": "log_customs",
        "title": "跨境清关资料审核",
        "description": "跨境清关资料审核，校验报关单、发票、装箱单、HS 编码和监管证件完整性。",
        "query": "跨境物流要检查报关单、发票、装箱单和 HS 编码是否完整，应该匹配哪条？",
        "keywords": ["跨境", "清关", "HS编码", "装箱单"],
    },
    {
        "industry": "物流",
        "slug": "log_warehouse",
        "title": "仓储波次拣选",
        "description": "仓储波次拣选系统，根据订单结构、库位、拣货路径、包装规则和截单时间生成波次任务。",
        "query": "仓库要按照库位、截单时间和包装规则生成拣货波次，找哪个能力？",
        "keywords": ["仓储", "波次", "拣选", "截单"],
    },
    {
        "industry": "物流",
        "slug": "log_fleet",
        "title": "车队油耗异常分析",
        "description": "车队油耗异常分析，结合 GPS 轨迹、怠速时长、载重、司机行为和加油记录识别异常。",
        "query": "车队管理要用 GPS、怠速、载重和加油记录发现油耗异常，应该召回哪个？",
        "keywords": ["车队", "油耗", "GPS", "怠速"],
    },
    {
        "industry": "教育",
        "slug": "edu_adaptive",
        "title": "自适应学习推荐",
        "description": "自适应学习推荐系统，根据知识点掌握度、错题、学习时长和目标考试推荐练习路径。",
        "query": "在线教育要按知识点掌握度、错题和目标考试推荐练习路径，找哪个方案？",
        "keywords": ["自适应学习", "知识点", "错题", "练习路径"],
    },
    {
        "industry": "教育",
        "slug": "edu_exam",
        "title": "在线考试防作弊",
        "description": "在线考试防作弊系统，融合人脸核验、视线偏移、切屏行为、声音异常和答题节奏监控。",
        "query": "远程考试要检测人脸、视线偏移、切屏和声音异常，应该命中哪项？",
        "keywords": ["在线考试", "防作弊", "切屏", "视线"],
    },
    {
        "industry": "教育",
        "slug": "edu_marking",
        "title": "智能阅卷评分",
        "description": "智能阅卷评分能力，识别手写答案、主观题语义、评分细则和异常卷面，辅助教师复核。",
        "query": "老师希望自动识别手写答案并按评分细则给主观题打分，找哪个能力？",
        "keywords": ["智能阅卷", "手写", "主观题", "评分细则"],
    },
    {
        "industry": "教育",
        "slug": "edu_lms",
        "title": "学习行为分析",
        "description": "学习行为分析平台，追踪课程观看、互动、作业提交、测验结果和学习预警。",
        "query": "学校要追踪课程观看、互动和作业提交，并给出学习预警，应该匹配哪条？",
        "keywords": ["学习行为", "课程观看", "作业", "预警"],
    },
    {
        "industry": "教育",
        "slug": "edu_knowledge",
        "title": "课程知识图谱",
        "description": "课程知识图谱构建，抽取章节、概念、先修关系、例题和考点，支持智能问答与推荐。",
        "query": "教研团队要抽取章节概念、先修关系和考点来做课程知识图谱，召回哪个？",
        "keywords": ["知识图谱", "先修关系", "章节", "考点"],
    },
    {
        "industry": "能源",
        "slug": "ene_power_load",
        "title": "电力负荷预测",
        "description": "电力负荷预测模型，融合天气、节假日、用电曲线、行业产能和需求响应信号。",
        "query": "电网调度要结合天气、节假日和用电曲线预测负荷，用哪个能力？",
        "keywords": ["电力", "负荷预测", "天气", "需求响应"],
    },
    {
        "industry": "能源",
        "slug": "ene_pv",
        "title": "光伏发电功率预测",
        "description": "光伏发电功率预测，结合辐照度、云量、组件温度、逆变器状态和历史出力曲线。",
        "query": "新能源场站要用辐照度、云量和逆变器状态预测光伏出力，应该匹配哪条？",
        "keywords": ["光伏", "辐照度", "逆变器", "出力"],
    },
    {
        "industry": "能源",
        "slug": "ene_battery",
        "title": "储能电池健康评估",
        "description": "储能电池健康评估，分析 SOC、SOH、温度、电压一致性和循环次数，识别热失控风险。",
        "query": "储能系统要分析 SOC、SOH、电压一致性并预警热失控，用哪个文档？",
        "keywords": ["储能", "SOC", "SOH", "热失控"],
    },
    {
        "industry": "能源",
        "slug": "ene_carbon",
        "title": "碳排放核算",
        "description": "碳排放核算平台，采集能源消耗、排放因子、生产批次和供应链数据，生成核算报告。",
        "query": "企业要根据能源消耗、排放因子和供应链数据生成碳核算报告，找哪个方案？",
        "keywords": ["碳排放", "排放因子", "供应链", "核算"],
    },
    {
        "industry": "能源",
        "slug": "ene_wind",
        "title": "风机故障诊断",
        "description": "风机故障诊断模型，分析齿轮箱振动、偏航系统、叶片状态和 SCADA 告警日志。",
        "query": "风电运维要通过齿轮箱振动、偏航系统和 SCADA 告警判断风机故障，命中哪个？",
        "keywords": ["风机", "齿轮箱", "SCADA", "偏航"],
    },
    {
        "industry": "政务",
        "slug": "gov_hotline",
        "title": "政务热线工单分派",
        "description": "政务热线工单分派，识别诉求主题、属地、责任部门、紧急程度和历史重复投诉。",
        "query": "12345 热线要根据诉求主题、属地和责任部门自动派单，应该召回哪项？",
        "keywords": ["政务热线", "工单", "属地", "责任部门"],
    },
    {
        "industry": "政务",
        "slug": "gov_approval",
        "title": "行政审批材料预审",
        "description": "行政审批材料预审，校验证照、申请表、法人信息、经营范围和缺失材料清单。",
        "query": "政务大厅想自动检查申请表、证照、法人信息和缺失材料，用哪个能力？",
        "keywords": ["行政审批", "材料预审", "证照", "法人"],
    },
    {
        "industry": "政务",
        "slug": "gov_emergency",
        "title": "应急事件研判",
        "description": "应急事件研判系统，汇聚报警、舆情、视频、物资和队伍位置，评估事件等级。",
        "query": "应急中心要把报警、舆情、视频和物资队伍位置汇总判断事件等级，匹配哪个？",
        "keywords": ["应急", "事件研判", "舆情", "物资"],
    },
    {
        "industry": "政务",
        "slug": "gov_license",
        "title": "证照到期提醒",
        "description": "证照到期提醒能力，管理企业许可证、人员资质、年检周期和续办材料通知。",
        "query": "监管部门要提醒企业许可证、人员资质和年检周期快到期，应该命中哪条？",
        "keywords": ["证照", "到期", "年检", "续办"],
    },
    {
        "industry": "政务",
        "slug": "gov_public_opinion",
        "title": "网络舆情分析",
        "description": "网络舆情分析平台，监测热点话题、情感倾向、传播路径和重点账号，形成处置建议。",
        "query": "宣传部门要监测热点话题、情感倾向和传播路径并给处置建议，找哪个方案？",
        "keywords": ["舆情", "情感倾向", "传播路径", "处置建议"],
    },
    {
        "industry": "房地产",
        "slug": "re_property",
        "title": "物业报修派单",
        "description": "物业报修派单系统，识别报修类别、楼栋房号、维修班组、 SLA 时限和回访状态。",
        "query": "物业系统要根据报修类别、楼栋房号和 SLA 自动派给维修班组，应该召回哪条？",
        "keywords": ["物业", "报修", "SLA", "维修班组"],
    },
    {
        "industry": "房地产",
        "slug": "re_house_match",
        "title": "房源客源匹配",
        "description": "房源客源匹配能力，结合预算、户型、地段、通勤、学区和客户偏好推荐房源。",
        "query": "中介要按客户预算、户型、通勤和学区偏好推荐房源，用哪个能力？",
        "keywords": ["房源", "客源", "预算", "学区"],
    },
    {
        "industry": "房地产",
        "slug": "re_bim",
        "title": "BIM 施工进度协同",
        "description": "BIM 施工进度协同，关联模型构件、施工计划、现场照片、质量问题和整改闭环。",
        "query": "项目部要把 BIM 构件、施工计划、现场照片和整改闭环关联起来，匹配哪个？",
        "keywords": ["BIM", "施工进度", "构件", "整改"],
    },
    {
        "industry": "房地产",
        "slug": "re_sales",
        "title": "楼盘销售线索评分",
        "description": "楼盘销售线索评分，分析到访、认筹、渠道来源、预算匹配和跟进记录，预测成交概率。",
        "query": "案场要根据到访、认筹、渠道来源和跟进记录预测客户成交概率，找哪项？",
        "keywords": ["楼盘", "线索评分", "认筹", "成交概率"],
    },
    {
        "industry": "房地产",
        "slug": "re_iot",
        "title": "智慧社区门禁联动",
        "description": "智慧社区门禁联动，管理人脸识别、访客预约、电梯权限、车辆道闸和异常通行告警。",
        "query": "社区要做人脸门禁、访客预约、电梯权限和车辆道闸联动，应该命中哪个文档？",
        "keywords": ["智慧社区", "门禁", "访客", "道闸"],
    },
    {
        "industry": "农业",
        "slug": "agr_irrigation",
        "title": "智慧灌溉控制",
        "description": "智慧灌溉控制系统，结合土壤湿度、气象、作物生长期、阀门状态和用水计划。",
        "query": "农场要根据土壤湿度、天气和作物生长期自动控制灌溉阀门，找哪个方案？",
        "keywords": ["灌溉", "土壤湿度", "作物", "阀门"],
    },
    {
        "industry": "农业",
        "slug": "agr_pest",
        "title": "病虫害图像识别",
        "description": "病虫害图像识别模型，分析叶片斑点、虫害痕迹、作物品种和发生阶段，给出防治建议。",
        "query": "种植户上传叶片照片后想识别病虫害并获得防治建议，用哪个能力？",
        "keywords": ["病虫害", "叶片", "防治", "图像识别"],
    },
    {
        "industry": "农业",
        "slug": "agr_trace",
        "title": "农产品溯源",
        "description": "农产品溯源平台，记录地块、农事操作、投入品、采收批次、仓储运输和质检报告。",
        "query": "合作社要记录地块、农事、投入品和采收批次来做产品溯源，应该召回哪条？",
        "keywords": ["农产品", "溯源", "地块", "采收批次"],
    },
    {
        "industry": "农业",
        "slug": "agr_yield",
        "title": "作物产量预测",
        "description": "作物产量预测模型，融合遥感指数、降雨、积温、土壤肥力和历史产量。",
        "query": "农业部门要用遥感指数、降雨、积温和土壤肥力预测作物产量，找哪个？",
        "keywords": ["产量预测", "遥感", "降雨", "土壤肥力"],
    },
    {
        "industry": "农业",
        "slug": "agr_livestock",
        "title": "畜牧养殖健康监测",
        "description": "畜牧养殖健康监测，采集采食量、体温、活动量、栏舍环境和疫苗记录，预警疾病风险。",
        "query": "养殖场要通过采食量、体温、活动量和疫苗记录预警疾病风险，匹配哪个能力？",
        "keywords": ["畜牧", "采食量", "体温", "疾病预警"],
    },
]


def _percentile(values: List[float], percent: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percent) - 1))
    return ordered[index]


def _latency_summary(values: List[float]) -> Dict[str, float]:
    if not values:
        return {
            "avg": 0.0,
            "min": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "max": 0.0,
        }
    return {
        "avg": round(mean(values), 2),
        "min": round(min(values), 2),
        "p50": round(_percentile(values, 0.50), 2),
        "p95": round(_percentile(values, 0.95), 2),
        "max": round(max(values), 2),
    }


def _build_report_path(kind: str, timestamp: str) -> Path:
    """构造 Phase E 评测报告路径。"""
    return REPORTS_DIR / f"{timestamp}-{kind}.json"


def _metric_summary(evaluation: Dict[str, Any]) -> Dict[str, Any]:
    """提取 Phase E 统一指标摘要。"""
    latency = evaluation.get("latency_ms", {}) or {}
    metrics = {
        "recall@1": evaluation.get("top1_accuracy", 0.0),
        "recall@3": evaluation.get("top3_recall", 0.0),
        "recall@5": evaluation.get("top5_recall", 0.0),
        "mean_latency_ms": latency.get("avg", 0.0),
        "p50_latency_ms": latency.get("p50", 0.0),
        "p95_latency_ms": latency.get("p95", 0.0),
    }
    metrics.update(_stage_metric_summary(evaluation.get("stage_latency_ms", {}) or {}))
    return metrics


def _stage_metric_summary(stage_latency: Dict[str, Any]) -> Dict[str, float]:
    """提取 embedding/es/milvus/graph/rerank 阶段平均耗时。"""
    return {
        metric_name: (stage_latency.get(stage_name, {}) or {}).get("avg", 0.0)
        for metric_name, stage_name in STAGE_LATENCY_KEYS.items()
    }


def _rerank_decision_summary(query_profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总每条查询的 Rerank 决策，用于跳过阈值调参。"""
    decisions = [
        item.get("profile", {}).get("rerank_decision", {})
        for item in query_profiles
    ]
    skipped = [decision for decision in decisions if decision.get("skipped")]
    score_gaps = [
        float(decision.get("score_gap", 0) or 0)
        for decision in decisions
    ]
    candidate_counts = [
        int(decision.get("candidate_count", 0) or 0)
        for decision in decisions
    ]
    total = len(decisions)
    return {
        "query_count": total,
        "skip_count": len(skipped),
        "skip_rate": round(len(skipped) / total, 4) if total else 0.0,
        "score_gap": _latency_summary(score_gaps),
        "candidate_count": _latency_summary(candidate_counts),
    }


def _prewarm_external_clients() -> Dict[str, Any]:
    """预热外部检索客户端，避免首条查询承担兼容性探测成本。"""
    prewarm: Dict[str, Any] = {}

    started = time.perf_counter()
    try:
        connected = get_es_service().is_connected()
        prewarm["elasticsearch"] = {
            "connected": connected,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        prewarm["elasticsearch"] = {
            "connected": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
        }

    return prewarm


def _build_features(doc: Dict[str, Any]) -> Dict[str, Any]:
    entities = [{"name": keyword, "type": "keyword"} for keyword in doc["keywords"]]
    return {
        "category": doc["industry"],
        "tags": doc["keywords"],
        "entities": entities,
        "relations": [
            {
                "source": doc["industry"],
                "relation": "包含能力",
                "target": doc["title"],
            }
        ],
    }


async def _encode_in_batches(embedding_service: EmbeddingService, texts: List[str], batch_size: int) -> List[List[float]]:
    vectors: List[List[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        batch_vectors = await embedding_service.encode(batch)
        vectors.extend(batch_vectors)
    return vectors


def _select_docs(limit: int) -> List[Dict[str, Any]]:
    """按命令行 limit 选择本次评测数据集。"""
    return DOCS[:max(1, min(limit, len(DOCS)))]


async def _insert_dataset(run_id: str, eval_type: str, docs: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    embedding_service = EmbeddingService(use_cache=False)
    milvus_service = MilvusService()
    es_service = get_es_service()
    selected_docs = docs or DOCS

    await es_service.create_index_if_not_exists(Config.ES_SKILL_INDEX)

    started = time.perf_counter()
    descriptions = [doc["description"] for doc in selected_docs]
    vectors = await _encode_in_batches(embedding_service, descriptions, batch_size=10)

    milvus_documents = []
    es_documents = []
    for index, doc in enumerate(selected_docs):
        doc_id = f"{run_id}_{doc['slug']}"
        features = _build_features(doc)
        metadata = {
            "type": eval_type,
            "id": doc_id,
            "description": doc["description"],
            "industry": doc["industry"],
            "title": doc["title"],
            "run_id": run_id,
            "expected_slug": doc["slug"],
        }
        milvus_documents.append({
            "id": doc_id,
            "description": doc["description"],
            "vector": vectors[index],
            "metadata": metadata,
            "features": features,
        })
        es_documents.append({
            "doc_id": doc_id,
            "description": doc["description"],
            "metadata": metadata,
            "features": features,
        })

    milvus_result = await milvus_service.batch_insert(eval_type, milvus_documents)
    get_graph_retrieval_service().index_documents(milvus_documents)
    es_count = await es_service.index_documents(Config.ES_SKILL_INDEX, es_documents)
    if getattr(es_service.client, "indices", None) is not None:
        with suppress(Exception):
            es_service.client.indices.refresh(index=Config.ES_SKILL_INDEX)

    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "milvus_inserted": milvus_result.get("inserted_count", 0),
        "es_indexed": es_count,
        "ingest_ms": round(elapsed_ms, 2),
    }


async def _evaluate_queries(
    run_id: str,
    eval_type: str,
    repeat: int = 1,
    docs: List[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """执行评测查询，支持重复轮次用于观察缓存收益。"""
    runs = []
    for run_index in range(max(1, repeat)):
        run_summary = await _evaluate_query_once_with_optional_docs(run_id, eval_type, docs)
        run_summary["run_index"] = run_index + 1
        run_summary["cache_stats"] = get_cache_service().get_stats()
        runs.append(run_summary)
    if len(runs) == 1:
        return runs[0]
    return {
        **runs[-1],
        "runs": runs,
    }


async def _evaluate_query_once_with_optional_docs(
    run_id: str,
    eval_type: str,
    docs: List[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """兼容旧测试替身：只有显式传入 docs 时才传第三参。"""
    if docs is None:
        return await _evaluate_query_once(run_id, eval_type)
    return await _evaluate_query_once(run_id, eval_type, docs)


async def _evaluate_query_once(run_id: str, eval_type: str, docs: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """执行单轮评测查询。"""
    selected_docs = docs or DOCS
    latencies: List[float] = []
    ranks: List[int] = []
    misses: List[Dict[str, Any]] = []
    non_top1: List[Dict[str, Any]] = []
    per_industry_latencies: Dict[str, List[float]] = defaultdict(list)
    stage_timings: Dict[str, List[float]] = defaultdict(list)
    query_profiles: List[Dict[str, Any]] = []

    graph_documents = [
        {
            "id": f"{run_id}_{doc['slug']}",
            "description": doc["description"],
            "metadata": {
                "type": eval_type,
                "id": f"{run_id}_{doc['slug']}",
                "description": doc["description"],
                "industry": doc["industry"],
                "title": doc["title"],
                "run_id": run_id,
                "expected_slug": doc["slug"],
            },
            "features": _build_features(doc),
        }
        for doc in selected_docs
    ]
    get_graph_retrieval_service().rebuild(graph_documents)

    for doc in selected_docs:
        expected_id = f"{run_id}_{doc['slug']}"
        started = time.perf_counter()
        pipeline_result = await run_search_pipeline_with_profile(
            "industry50_eval",
            SearchRequest(
                input=doc["query"],
                type=eval_type,
                topK=10,
                threshold=0,
                enableFeatureBoost=False,
            ),
        )
        results = pipeline_result.results
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        per_industry_latencies[doc["industry"]].append(latency_ms)
        for stage, stage_ms in pipeline_result.profile.get("timings_ms", {}).items():
            stage_timings[stage].append(stage_ms)
        query_profiles.append({
            "industry": doc["industry"],
            "slug": doc["slug"],
            "query": doc["query"],
            "expected_id": expected_id,
            "latency_ms": round(latency_ms, 2),
            "profile": pipeline_result.profile,
        })

        result_ids = [item.metadata.get("id") for item in results]
        rank = result_ids.index(expected_id) + 1 if expected_id in result_ids else 0
        ranks.append(rank)
        if rank == 0:
            misses.append({
                "industry": doc["industry"],
                "expected_id": expected_id,
                "query": doc["query"],
                "top_ids": result_ids[:10],
            })
        elif rank != 1:
            non_top1.append({
                "industry": doc["industry"],
                "expected_id": expected_id,
                "expected_rank": rank,
                "query": doc["query"],
                "top_ids": result_ids[:10],
            })
        get_rag_evaluation_service().record_case(
            query=doc["query"],
            optimized_query=doc["query"],
            retrieved_ids=result_ids[:10],
            miss_reason="unknown" if rank else "recall_miss",
            human_label="hit" if rank else "miss",
            user_id="industry50_eval",
            request_id=expected_id,
            retrieval_strategy=Config.RAG_RETRIEVAL_STRATEGY,
            latency_ms=round(latency_ms, 2),
        )

    total = len(ranks)
    rank_distribution = {
        str(rank): sum(1 for item in ranks if item == rank)
        for rank in sorted(set(ranks))
    }
    summary = {
        "query_count": total,
        "top1_accuracy": round(sum(1 for rank in ranks if rank == 1) / total, 4),
        "top3_recall": round(sum(1 for rank in ranks if 1 <= rank <= 3) / total, 4),
        "top5_recall": round(sum(1 for rank in ranks if 1 <= rank <= 5) / total, 4),
        "top10_recall": round(sum(1 for rank in ranks if 1 <= rank <= 10) / total, 4),
        "mrr": round(sum((1 / rank) if rank else 0 for rank in ranks) / total, 4),
        "latency_ms": _latency_summary(latencies),
        "stage_latency_ms": {
            stage: _latency_summary(values)
            for stage, values in sorted(stage_timings.items())
            if values
        },
        "rerank_decision_summary": _rerank_decision_summary(query_profiles),
        "query_profiles": query_profiles,
        "per_industry_avg_ms": {
            industry: round(mean(values), 2)
            for industry, values in sorted(per_industry_latencies.items())
        },
        "rank_distribution": rank_distribution,
        "non_top1": non_top1,
        "misses": misses,
    }
    return summary


def build_parser() -> argparse.ArgumentParser:
    """构造 industry50 评测命令行参数。"""
    parser = argparse.ArgumentParser(description="50 条跨行业 RAG 真实链路评测")
    parser.add_argument("--run-id", default="", help="复用已有评测 run_id")
    parser.add_argument("--eval-type", default="", help="复用已有评测 collection type")
    parser.add_argument("--skip-ingest", action="store_true", help="跳过写入，只重跑查询评测")
    parser.add_argument("--repeat", type=int, default=1, help="重复查询轮次，用于观察缓存收益")
    parser.add_argument("--rerank-cache", action="store_true", help="评测时启用 Rerank 缓存")
    parser.add_argument("--seed", type=int, default=DEFAULT_INDUSTRY50_SEED, help="固定评测随机种子")
    parser.add_argument("--strategy", choices=["rrf", "ragflow_weighted"], default=Config.RAG_RETRIEVAL_STRATEGY)
    parser.add_argument("--limit", type=int, default=len(DOCS), help="限制本次评测文档和查询数量")
    return parser


async def main() -> None:
    args = build_parser().parse_args()

    Config.DEBUG = False
    Config.RAG_RETRIEVAL_STRATEGY = args.strategy
    if args.rerank_cache:
        Config.RERANK_CACHE_ENABLED = True

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = args.run_id or f"recall_eval_industry50_{run_timestamp}"
    eval_type = args.eval_type or f"eval_industry50_{run_timestamp}"
    selected_docs = _select_docs(args.limit)

    print("RAG 50 条跨行业评测开始")
    print(f"run_id={run_id}")
    print(f"eval_type={eval_type}")
    print(f"es_index={Config.ES_SKILL_INDEX}")
    print(f"milvus_db={Config.MILVUS_DB}")
    print(f"repeat={max(1, args.repeat)}")
    print(f"rerank_cache_enabled={Config.RERANK_CACHE_ENABLED}")
    print(f"retrieval_strategy={args.strategy}")
    print(f"limit={len(selected_docs)}")

    ingest = {"skipped": True} if args.skip_ingest else await _insert_dataset(run_id, eval_type, selected_docs)
    prewarm = _prewarm_external_clients()
    evaluation = await _evaluate_queries(run_id, eval_type, repeat=max(1, args.repeat), docs=selected_docs)
    report = {
        "run_id": run_id,
        "eval_type": eval_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset": {
            "doc_count": len(selected_docs),
            "industry_count": len({doc["industry"] for doc in selected_docs}),
            "industries": sorted({doc["industry"] for doc in selected_docs}),
        },
        "settings": {
            "seed": args.seed,
            "limit": len(selected_docs),
            "repeat": max(1, args.repeat),
            "retrieval_strategy": args.strategy,
            "rerank_cache_enabled": Config.RERANK_CACHE_ENABLED,
            "rerank_candidate_limit": Config.RAG_RERANK_CANDIDATE_LIMIT,
        },
        "metrics": _metric_summary(evaluation),
        "ingest": ingest,
        "prewarm": prewarm,
        "evaluation": evaluation,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = _build_report_path(REPORT_KIND_INDUSTRY50, report_timestamp)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    output_path.write_text(report_json, encoding="utf-8")
    LAST_REPORT_PATH.parent.mkdir(exist_ok=True)
    LAST_REPORT_PATH.write_text(report_json, encoding="utf-8")

    print(report_json)
    print(f"report_path={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
