#!/usr/bin/env python
"""
批量插入100条测试数据

行业覆盖: IT/互联网、金融、医疗健康、教育、制造业、零售电商、
          房地产、物流运输、媒体娱乐、能源环保

@author lvdaxianerplus
@date 2026-04-18
"""

import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.embedding_service import EmbeddingService
from app.services.feature_extract_service import get_feature_extract_service
from app.services.milvus_service import MilvusService
from app.services.es_service import get_es_service


async def insert_one(embedding_service, feature_extract_service, milvus_service, es_service, item):
    """插入单条数据"""
    vector = await embedding_service.encode(item['description'])
    features = await feature_extract_service.extract_features(item['description'])

    collection = 'studio_skill' if item['type'] == 'skill' else 'studio_asset'

    milvus_service.insert(
        collection=collection,
        doc_id=item['id'],
        description=item['description'],
        vector=vector,
        metadata={'type': item['type'], 'id': item['id']},
        features=features
    )

    es_service.index_document(
        index=collection,
        doc_id=item['id'],
        document={
            'id': item['id'],
            'description': item['description'],
            'collection': item['type'],
            'features': features,
            'vector_id': item['id']
        }
    )
    return {'id': item['id'], 'features': features}


async def main():
    """主函数"""
    print("=" * 60)
    print("RAG 批量插入测试数据")
    print("=" * 60)

    embedding_service = EmbeddingService()
    feature_extract_service = get_feature_extract_service()
    milvus_service = MilvusService()
    es_service = get_es_service()

    test_data = [
        # IT/互联网行业 (10条)
        {'id': 'it001', 'description': 'Python机器学习教程 讲解scikit-learn回归分类聚类', 'type': 'skill'},
        {'id': 'it002', 'description': 'React组件库 包含按钮输入框弹窗 支持主题定制', 'type': 'skill'},
        {'id': 'it003', 'description': 'Docker容器化部署指南 K8S集群管理', 'type': 'skill'},
        {'id': 'it004', 'description': 'MySQL数据库优化 索引设计SQL调优', 'type': 'skill'},
        {'id': 'it005', 'description': 'GraphQL API设计 RESTful接口转换', 'type': 'skill'},
        {'id': 'it006', 'description': 'Redis缓存架构 分布式Session管理', 'type': 'skill'},
        {'id': 'it007', 'description': 'Git协作开发 分支管理代码审查流程', 'type': 'skill'},
        {'id': 'it008', 'description': 'TypeScript类型系统 泛型接口类型守卫', 'type': 'skill'},
        {'id': 'it009', 'description': '微服务架构设计 API网关服务注册发现', 'type': 'skill'},
        {'id': 'it010', 'description': '前端性能优化 Webpack打包体积优化', 'type': 'skill'},
        # 金融行业 (10条)
        {'id': 'fin001', 'description': '量化交易策略 Python Pandas金融数据分析', 'type': 'skill'},
        {'id': 'fin002', 'description': '区块链智能合约 Solidity以太坊开发', 'type': 'skill'},
        {'id': 'fin003', 'description': '风控模型设计 信用评分卡开发', 'type': 'skill'},
        {'id': 'fin004', 'description': '财务报表分析 Excel财务比率计算', 'type': 'skill'},
        {'id': 'fin005', 'description': '保险产品设计 精算模型定价', 'type': 'skill'},
        {'id': 'fin006', 'description': '投资组合优化 Markowitz均值方差模型', 'type': 'skill'},
        {'id': 'fin007', 'description': '反欺诈检测 机器学习异常识别', 'type': 'skill'},
        {'id': 'fin008', 'description': '支付系统设计 第三方支付集成', 'type': 'skill'},
        {'id': 'fin009', 'description': '税务筹划指南 企业所得税优化', 'type': 'skill'},
        {'id': 'fin010', 'description': '资产配置策略 养老金投资管理', 'type': 'skill'},
        # 医疗健康 (10条)
        {'id': 'med001', 'description': '医学影像诊断 CNN卷积神经网络肺部X光', 'type': 'skill'},
        {'id': 'med002', 'description': '药物分子设计 AI靶点预测', 'type': 'skill'},
        {'id': 'med003', 'description': '电子病历系统 HIS医院信息系统', 'type': 'skill'},
        {'id': 'med004', 'description': '基因序列分析 BLAST比对算法', 'type': 'skill'},
        {'id': 'med005', 'description': '手术机器人控制 达芬奇系统', 'type': 'skill'},
        {'id': 'med006', 'description': '健康监测手环 心率血氧睡眠分析', 'type': 'skill'},
        {'id': 'med007', 'description': '医疗数据挖掘 疾病预测模型', 'type': 'skill'},
        {'id': 'med008', 'description': '中药配方分析 君臣佐使配伍', 'type': 'skill'},
        {'id': 'med009', 'description': '医疗保险理赔 自动核赔系统', 'type': 'skill'},
        {'id': 'med010', 'description': '远程医疗平台 在线问诊视频会诊', 'type': 'skill'},
        # 教育行业 (10条)
        {'id': 'edu001', 'description': '自适应学习系统 AI推荐算法个性化教学', 'type': 'skill'},
        {'id': 'edu002', 'description': '在线考试系统 防作弊人脸识别', 'type': 'skill'},
        {'id': 'edu003', 'description': '知识图谱构建 自然语言处理实体抽取', 'type': 'skill'},
        {'id': 'edu004', 'description': '学习行为分析 学习轨迹数据挖掘', 'type': 'skill'},
        {'id': 'edu005', 'description': '课件制作工具 PPT动画交互设计', 'type': 'skill'},
        {'id': 'edu006', 'description': '智能阅卷系统 OCR手写识别评分', 'type': 'skill'},
        {'id': 'edu007', 'description': '家教匹配平台 算法推荐最优教师', 'type': 'skill'},
        {'id': 'edu008', 'description': 'VR虚拟实验室 物理化学仿真实验', 'type': 'skill'},
        {'id': 'edu009', 'description': '课程推荐系统 协同过滤内容推荐', 'type': 'skill'},
        {'id': 'edu010', 'description': '语言学习APP 语音识别口语评分', 'type': 'skill'},
        # 制造业 (10条)
        {'id': 'mfg001', 'description': '3D飞机模型设计 CATIA三维建模', 'type': 'skill'},
        {'id': 'mfg002', 'description': '工业机器人编程 ABB示教编程', 'type': 'skill'},
        {'id': 'mfg003', 'description': 'PLC梯形图设计 西门子S7编程', 'type': 'skill'},
        {'id': 'mfg004', 'description': 'MES制造执行系统 生产工单管理', 'type': 'skill'},
        {'id': 'mfg005', 'description': '质量检测系统 机器视觉缺陷识别', 'type': 'skill'},
        {'id': 'mfg006', 'description': '供应链管理系统 SAP MM模块', 'type': 'skill'},
        {'id': 'mfg007', 'description': '数字孪生建模 工厂仿真虚实映射', 'type': 'skill'},
        {'id': 'mfg008', 'description': '设备预测性维护 振动信号分析', 'type': 'skill'},
        {'id': 'mfg009', 'description': '柔性制造系统 自动导引小车AGV', 'type': 'skill'},
        {'id': 'mfg010', 'description': '工艺参数优化 响应面分析RSM', 'type': 'skill'},
        # 零售电商 (10条)
        {'id': 'ret001', 'description': '推荐系统设计 电商个性化商品推荐', 'type': 'skill'},
        {'id': 'ret002', 'description': '用户画像分析 RFM模型忠诚度分析', 'type': 'skill'},
        {'id': 'ret003', 'description': '库存管理系统 ABC分类动态补货', 'type': 'skill'},
        {'id': 'ret004', 'description': '价格监控系统 竞品价格抓取', 'type': 'skill'},
        {'id': 'ret005', 'description': 'CRM客户关系管理 会员积分体系', 'type': 'skill'},
        {'id': 'ret006', 'description': '物流路径规划 车辆调度VRP', 'type': 'skill'},
        {'id': 'ret007', 'description': '商品搜索优化 ES搜索引擎', 'type': 'skill'},
        {'id': 'ret008', 'description': '订单履约系统 仓储管理系统WMS', 'type': 'skill'},
        {'id': 'ret009', 'description': '促销活动设计 满减优惠券策略', 'type': 'skill'},
        {'id': 'ret010', 'description': '商品销量预测 时序预测Prophet', 'type': 'skill'},
        # 房地产 (10条)
        {'id': 're001', 'description': '房价预测模型 梯度提升树XGBoost', 'type': 'skill'},
        {'id': 're002', 'description': '楼盘营销系统 CRM渠道管理', 'type': 'skill'},
        {'id': 're003', 'description': '租房平台设计 房源匹配推荐', 'type': 'skill'},
        {'id': 're004', 'description': '智能家居系统 IoT设备联动', 'type': 'skill'},
        {'id': 're005', 'description': '物业管理系统 报事报修工单', 'type': 'skill'},
        {'id': 're006', 'description': 'BIM建筑信息模型 Revit建模', 'type': 'skill'},
        {'id': 're007', 'description': '室内装修设计 3D效果图渲染', 'type': 'skill'},
        {'id': 're008', 'description': '写字楼招商系统 租户管理', 'type': 'skill'},
        {'id': 're009', 'description': '房产中介管理系统 房源客源匹配', 'type': 'skill'},
        {'id': 're010', 'description': '智慧社区平台 人脸识别门禁', 'type': 'skill'},
        # 物流运输 (10条)
        {'id': 'log001', 'description': '车队管理系统 GPS定位轨迹追踪', 'type': 'skill'},
        {'id': 'log002', 'description': '仓储机器人控制 AMR自主移动机器人', 'type': 'skill'},
        {'id': 'log003', 'description': '跨境物流系统 清关报检流程', 'type': 'skill'},
        {'id': 'log004', 'description': '无人机配送路径规划 最后一公里', 'type': 'skill'},
        {'id': 'log005', 'description': '集装箱码头管理 TOS操作系统', 'type': 'skill'},
        {'id': 'log006', 'description': '危险品运输监控 物联网传感器', 'type': 'skill'},
        {'id': 'log007', 'description': '多式联运系统 铁公水多式联运', 'type': 'skill'},
        {'id': 'log008', 'description': '冷链物流系统 温湿度监控', 'type': 'skill'},
        {'id': 'log009', 'description': '同城配送调度 骑手路径优化', 'type': 'skill'},
        {'id': 'log010', 'description': '物流大数据分析 供应链可视化', 'type': 'skill'},
        # 媒体娱乐 (10条)
        {'id': 'mec001', 'description': '短视频推荐算法 抖音快手推荐系统', 'type': 'skill'},
        {'id': 'mec002', 'description': '内容审核系统 NLP文本分类涉黄涉政', 'type': 'skill'},
        {'id': 'mec003', 'description': '用户增长系统 AARRR漏斗分析', 'type': 'skill'},
        {'id': 'mec004', 'description': '音乐推荐系统 协同过滤歌单生成', 'type': 'skill'},
        {'id': 'mec005', 'description': '影视特效制作 Nuke合成Maya绑定', 'type': 'skill'},
        {'id': 'mec006', 'description': '游戏AI设计 强化学习NPC行为', 'type': 'skill'},
        {'id': 'mec007', 'description': '直播带货系统 弹幕互动实时推荐', 'type': 'skill'},
        {'id': 'mec008', 'description': '舆情监控系统 社交媒体情感分析', 'type': 'skill'},
        {'id': 'mec009', 'description': '内容标签系统 自动打标签分类', 'type': 'skill'},
        {'id': 'mec010', 'description': '广告投放系统 DSP实时竞价', 'type': 'skill'},
        # 能源环保 (10条)
        {'id': 'ene001', 'description': '光伏发电预测 天气数据融合时序预测', 'type': 'skill'},
        {'id': 'ene002', 'description': '风电场运维 齿轮箱故障诊断', 'type': 'skill'},
        {'id': 'ene003', 'description': '智能电网调度 负荷预测需求响应', 'type': 'skill'},
        {'id': 'ene004', 'description': '锂电池BMS管理 SOC估算均衡管理', 'type': 'skill'},
        {'id': 'ene005', 'description': '污水处理系统 活性污泥法工艺', 'type': 'skill'},
        {'id': 'ene006', 'description': '空气质量监测 PM2.5预测溯源分析', 'type': 'skill'},
        {'id': 'ene007', 'description': '碳排放核算 LCA生命周期评估', 'type': 'skill'},
        {'id': 'ene008', 'description': '固废管理系统 垃圾分类处理', 'type': 'skill'},
        {'id': 'ene009', 'description': '智慧农业系统 土壤传感器灌溉控制', 'type': 'skill'},
        {'id': 'ene010', 'description': '能耗管理平台 建筑节能优化', 'type': 'skill'},
    ]

    success_count = 0
    fail_count = 0

    for item in test_data:
        try:
            result = await insert_one(
                embedding_service, feature_extract_service, milvus_service, es_service, item
            )
            success_count += 1
            tags_preview = result['features'].get('tags', [])[:3]
            print(f"[{success_count:3d}] {item['id']}: {result['features'].get('category', 'N/A'):8s} | tags={tags_preview}")
        except Exception as e:
            fail_count += 1
            print(f"[FAIL] {item['id']}: {str(e)[:80]}")

    print("=" * 60)
    print(f"插入完成: {success_count} 成功, {fail_count} 失败")
    print("=" * 60)

    return success_count, fail_count


if __name__ == "__main__":
    asyncio.run(main())