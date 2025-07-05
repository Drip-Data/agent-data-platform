#!/usr/bin/env python3
"""
🔍 智能查询优化器 (Smart Query Optimizer)
优化工具查询的精确度和成功率，减少无效尝试
"""

import logging
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """查询类型"""
    FACTUAL = "factual"           # 事实查询
    PRICE = "price"               # 价格查询  
    DEFINITION = "definition"     # 定义查询
    COMPARISON = "comparison"     # 比较查询
    ANALYSIS = "analysis"         # 分析查询
    TECHNICAL = "technical"       # 技术查询
    CURRENT_EVENT = "current_event"  # 时事查询


class QueryQuality(Enum):
    """查询质量"""
    EXCELLENT = "excellent"      # 优秀 - 精确、具体
    GOOD = "good"               # 良好 - 较为明确  
    AVERAGE = "average"         # 一般 - 模糊但可用
    POOR = "poor"               # 较差 - 过于宽泛
    VERY_POOR = "very_poor"     # 很差 - 无法使用


@dataclass
class QueryAnalysis:
    """查询分析结果"""
    original_query: str
    query_type: QueryType
    quality: QueryQuality
    specificity_score: float  # 0-1, 越高越具体
    optimization_suggestions: List[str]
    optimized_queries: List[str]
    confidence: float


@dataclass  
class QueryPattern:
    """查询模式"""
    pattern: str
    query_type: QueryType
    quality_indicators: Dict[str, float]
    optimization_rules: List[str]


class SmartQueryOptimizer:
    """
    🔍 智能查询优化器
    
    功能：
    1. 分析查询质量和类型
    2. 提供查询优化建议
    3. 学习成功/失败模式
    4. 生成更精确的查询变体
    """
    
    def __init__(self):
        """初始化查询优化器"""
        self.query_patterns = self._load_query_patterns()
        self.success_history: Dict[str, List[Dict]] = {}  # 成功查询历史
        self.failure_history: Dict[str, List[Dict]] = {}  # 失败查询历史
        self.optimization_rules = self._load_optimization_rules()
        
        logger.info("🔍 SmartQueryOptimizer initialized")
    
    def _load_query_patterns(self) -> List[QueryPattern]:
        """加载查询模式"""
        return [
            # 定义查询模式
            QueryPattern(
                pattern=r"(什么是|what is|define|definition of)\s+(.+)",
                query_type=QueryType.DEFINITION,
                quality_indicators={
                    "specific_term": 0.8,
                    "context_provided": 0.3,
                    "institution_mentioned": 0.6
                },
                optimization_rules=[
                    "add_context_keywords",
                    "include_institution_name", 
                    "use_official_terminology"
                ]
            ),
            
            # 价格查询模式
            QueryPattern(
                pattern=r"(price|cost|价格|成本|股价).*?(stock|share|股票|公司)",
                query_type=QueryType.PRICE,
                quality_indicators={
                    "company_name": 0.9,
                    "ticker_symbol": 0.8,
                    "time_specific": 0.6,
                    "market_specified": 0.4
                },
                optimization_rules=[
                    "add_ticker_symbol",
                    "specify_market",
                    "add_time_context",
                    "use_financial_terms"
                ]
            ),
            
            # 事实查询模式
            QueryPattern(
                pattern=r"(who|what|when|where|why|how|谁|什么|何时|哪里|为什么|如何)",
                query_type=QueryType.FACTUAL,
                quality_indicators={
                    "specific_entities": 0.7,
                    "clear_question": 0.8,
                    "context_provided": 0.5
                },
                optimization_rules=[
                    "add_entity_context",
                    "clarify_question_scope",
                    "include_relevant_keywords"
                ]
            ),
            
            # 技术查询模式
            QueryPattern(
                pattern=r"(algorithm|method|technique|implementation|算法|方法|技术|实现)",
                query_type=QueryType.TECHNICAL,
                quality_indicators={
                    "technical_terms": 0.8,
                    "specific_domain": 0.7,
                    "clear_objective": 0.6
                },
                optimization_rules=[
                    "add_domain_context",
                    "specify_use_case",
                    "include_technical_keywords"
                ]
            ),
            
            # 比较查询模式
            QueryPattern(
                pattern=r"(compare|vs|versus|difference|比较|对比|区别)",
                query_type=QueryType.COMPARISON,
                quality_indicators={
                    "clear_entities": 0.9,
                    "comparison_criteria": 0.7,
                    "specific_aspects": 0.6
                },
                optimization_rules=[
                    "clarify_comparison_criteria",
                    "specify_entities_clearly",
                    "add_context_domain"
                ]
            )
        ]
    
    def _load_optimization_rules(self) -> Dict[str, callable]:
        """加载优化规则"""
        return {
            "add_context_keywords": self._add_context_keywords,
            "include_institution_name": self._include_institution_name,
            "use_official_terminology": self._use_official_terminology,
            "add_ticker_symbol": self._add_ticker_symbol,
            "specify_market": self._specify_market,
            "add_time_context": self._add_time_context,
            "use_financial_terms": self._use_financial_terms,
            "add_entity_context": self._add_entity_context,
            "clarify_question_scope": self._clarify_question_scope,
            "include_relevant_keywords": self._include_relevant_keywords,
            "add_domain_context": self._add_domain_context,
            "specify_use_case": self._specify_use_case,
            "include_technical_keywords": self._include_technical_keywords,
            "clarify_comparison_criteria": self._clarify_comparison_criteria,
            "specify_entities_clearly": self._specify_entities_clearly,
            "add_context_domain": self._add_context_domain
        }
    
    def analyze_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> QueryAnalysis:
        """
        🔍 分析查询质量和类型
        
        Args:
            query: 查询字符串
            context: 上下文信息
            
        Returns:
            QueryAnalysis: 查询分析结果
        """
        # 1. 确定查询类型
        query_type = self._identify_query_type(query)
        
        # 2. 评估查询质量
        quality, specificity_score = self._assess_query_quality(query, query_type)
        
        # 3. 生成优化建议
        suggestions = self._generate_optimization_suggestions(query, query_type, quality, context)
        
        # 4. 创建优化查询
        optimized_queries = self._create_optimized_queries(query, query_type, suggestions, context)
        
        # 5. 计算置信度
        confidence = self._calculate_confidence(query, query_type, specificity_score)
        
        analysis = QueryAnalysis(
            original_query=query,
            query_type=query_type,
            quality=quality,
            specificity_score=specificity_score,
            optimization_suggestions=suggestions,
            optimized_queries=optimized_queries,
            confidence=confidence
        )
        
        logger.info(f"🔍 查询分析完成: {query_type.value}, 质量: {quality.value}, 置信度: {confidence:.2f}")
        return analysis
    
    def _identify_query_type(self, query: str) -> QueryType:
        """识别查询类型"""
        query_lower = query.lower()
        
        # 优先进行关键词匹配，更准确
        if any(keyword in query_lower for keyword in ["什么是", "是什么", "what is", "define", "定义"]):
            return QueryType.DEFINITION
        elif any(keyword in query_lower for keyword in ["price", "cost", "股价", "价格", "$"]):
            return QueryType.PRICE
        elif any(keyword in query_lower for keyword in ["compare", "vs", "versus", "比较", "对比"]):
            return QueryType.COMPARISON
        elif any(keyword in query_lower for keyword in ["algorithm", "method", "implement", "算法", "方法", "实现"]):
            return QueryType.TECHNICAL
        elif any(keyword in query_lower for keyword in ["analyze", "analysis", "calculate", "分析", "计算"]):
            return QueryType.ANALYSIS
        elif any(keyword in query_lower for keyword in ["recent", "latest", "current", "最新", "当前", "news"]):
            return QueryType.CURRENT_EVENT
        
        # 按模式匹配
        for pattern in self.query_patterns:
            if re.search(pattern.pattern, query, re.IGNORECASE):
                return pattern.query_type
        
        # 默认为事实查询
        return QueryType.FACTUAL
    
    def _assess_query_quality(self, query: str, query_type: QueryType) -> Tuple[QueryQuality, float]:
        """评估查询质量"""
        specificity_score = 0.0
        quality_factors = []
        
        # 1. 长度评估
        word_count = len(query.split())
        if word_count >= 5:
            specificity_score += 0.2
            quality_factors.append("adequate_length")
        elif word_count <= 2:
            specificity_score -= 0.3
            quality_factors.append("too_short")
        
        # 2. 专有名词检测（包括中文机构名）
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', query)
        chinese_institutions = re.findall(r'(大学|学院|研究所|公司|机构)', query)
        acronyms = re.findall(r'\b[A-Z]{2,}\b', query)  # 缩写词如IORA
        
        total_specificity_indicators = len(proper_nouns) + len(chinese_institutions) + len(acronyms)
        if total_specificity_indicators > 0:
            specificity_score += 0.2 * total_specificity_indicators
            quality_factors.append("contains_specific_entities")
        
        # 3. 具体性指标
        specific_indicators = [
            r'\b\d{4}\b',  # 年份
            r'\$\d+',      # 价格
            r'\b[A-Z]{2,5}\b',  # 股票代码等
            r'\b(latest|current|recent|最新|当前|最近)\b',  # 时间限定
        ]
        
        for indicator in specific_indicators:
            if re.search(indicator, query, re.IGNORECASE):
                specificity_score += 0.1
                quality_factors.append("specific_indicator")
        
        # 4. 模糊性检测
        vague_terms = ["thing", "stuff", "something", "anything", "东西", "事情", "什么的"]
        if any(term in query.lower() for term in vague_terms):
            specificity_score -= 0.2
            quality_factors.append("contains_vague_terms")
        
        # 5. 类型特定评估
        specificity_score += self._type_specific_assessment(query, query_type)
        
        # 6. 确定质量等级
        specificity_score = max(0.0, min(1.0, specificity_score))
        
        if specificity_score >= 0.8:
            quality = QueryQuality.EXCELLENT
        elif specificity_score >= 0.6:
            quality = QueryQuality.GOOD
        elif specificity_score >= 0.4:
            quality = QueryQuality.AVERAGE
        elif specificity_score >= 0.2:
            quality = QueryQuality.POOR
        else:
            quality = QueryQuality.VERY_POOR
        
        return quality, specificity_score
    
    def _type_specific_assessment(self, query: str, query_type: QueryType) -> float:
        """类型特定的质量评估"""
        score_adjustment = 0.0
        
        if query_type == QueryType.DEFINITION:
            # 定义查询应该包含具体术语
            if len(re.findall(r'\b[A-Z]+\b', query)) > 0:  # 缩写词
                score_adjustment += 0.2
            if any(org in query.lower() for org in ["university", "college", "institute", "大学", "学院", "研究所"]):
                score_adjustment += 0.2
        
        elif query_type == QueryType.PRICE:
            # 价格查询应该包含公司名或代码
            if re.search(r'\b[A-Z]{1,5}\b', query):  # 可能的股票代码
                score_adjustment += 0.3
            if any(term in query.lower() for term in ["stock", "share", "equity", "股票", "股份"]):
                score_adjustment += 0.1
        
        elif query_type == QueryType.TECHNICAL:
            # 技术查询应该包含专业术语
            technical_terms = ["algorithm", "method", "implementation", "framework", "算法", "方法", "实现", "框架"]
            if any(term in query.lower() for term in technical_terms):
                score_adjustment += 0.2
        
        return score_adjustment
    
    def _generate_optimization_suggestions(self, query: str, query_type: QueryType, 
                                        quality: QueryQuality, context: Optional[Dict[str, Any]]) -> List[str]:
        """生成优化建议"""
        suggestions = []
        
        # 1. 基于质量的通用建议
        if quality in [QueryQuality.POOR, QueryQuality.VERY_POOR]:
            suggestions.append("查询过于宽泛，建议添加更具体的关键词")
            suggestions.append("考虑添加时间、地点或其他限定条件")
        
        # 2. 基于类型的特定建议
        pattern = next((p for p in self.query_patterns if p.query_type == query_type), None)
        if pattern:
            suggestions.extend(self._apply_pattern_suggestions(query, pattern))
        
        # 3. 基于上下文的建议
        if context:
            suggestions.extend(self._generate_context_based_suggestions(query, context))
        
        # 4. 基于历史的建议
        historical_suggestions = self._get_historical_suggestions(query, query_type)
        suggestions.extend(historical_suggestions)
        
        return list(set(suggestions))  # 去重
    
    def _apply_pattern_suggestions(self, query: str, pattern: QueryPattern) -> List[str]:
        """应用模式特定的建议"""
        suggestions = []
        
        for rule_name in pattern.optimization_rules:
            if rule_name in self.optimization_rules:
                try:
                    rule_func = self.optimization_rules[rule_name]
                    suggestion = rule_func(query, pattern)
                    if suggestion:
                        suggestions.append(suggestion)
                except Exception as e:
                    logger.warning(f"⚠️ 优化规则 {rule_name} 执行失败: {e}")
        
        return suggestions
    
    def _create_optimized_queries(self, query: str, query_type: QueryType, 
                                suggestions: List[str], context: Optional[Dict[str, Any]]) -> List[str]:
        """创建优化后的查询"""
        optimized_queries = []
        
        # 1. 基于建议创建优化查询
        for suggestion in suggestions[:3]:  # 最多3个建议
            optimized_query = self._apply_suggestion_to_query(query, suggestion, context)
            if optimized_query and optimized_query != query:
                optimized_queries.append(optimized_query)
        
        # 2. 基于类型创建特定优化
        type_optimized = self._create_type_specific_optimizations(query, query_type, context)
        optimized_queries.extend(type_optimized)
        
        # 3. 基于成功历史创建变体
        historical_optimized = self._create_historical_variations(query, query_type)
        optimized_queries.extend(historical_optimized)
        
        # 4. 去重并排序
        unique_queries = list(set(optimized_queries))
        return unique_queries[:5]  # 最多返回5个优化查询
    
    def _calculate_confidence(self, query: str, query_type: QueryType, specificity_score: float) -> float:
        """计算优化信心度"""
        base_confidence = specificity_score
        
        # 基于历史成功率调整
        historical_success_rate = self._get_historical_success_rate(query_type)
        
        # 基于查询复杂度调整
        complexity_factor = len(query.split()) / 10  # 简单的复杂度评估
        
        # 综合计算
        confidence = (base_confidence * 0.6 + 
                     historical_success_rate * 0.3 + 
                     complexity_factor * 0.1)
        
        return min(1.0, max(0.0, confidence))
    
    def record_query_result(self, query: str, query_type: QueryType, 
                          success: bool, result_content: Optional[str] = None):
        """
        📊 记录查询结果用于学习
        
        Args:
            query: 查询字符串
            query_type: 查询类型
            success: 是否成功
            result_content: 结果内容
        """
        record = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "result_content": result_content,
            "query_length": len(query.split()),
            "specificity_score": self._assess_query_quality(query, query_type)[1]
        }
        
        type_key = query_type.value
        
        if success:
            if type_key not in self.success_history:
                self.success_history[type_key] = []
            self.success_history[type_key].append(record)
            logger.info(f"✅ 记录成功查询: {query[:50]}...")
        else:
            if type_key not in self.failure_history:
                self.failure_history[type_key] = []
            self.failure_history[type_key].append(record)
            logger.info(f"❌ 记录失败查询: {query[:50]}...")
        
        # 限制历史记录大小
        self._trim_history()
    
    def _trim_history(self, max_records: int = 100):
        """修剪历史记录"""
        for type_key in self.success_history:
            if len(self.success_history[type_key]) > max_records:
                self.success_history[type_key] = self.success_history[type_key][-max_records:]
        
        for type_key in self.failure_history:
            if len(self.failure_history[type_key]) > max_records:
                self.failure_history[type_key] = self.failure_history[type_key][-max_records:]
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """获取优化统计信息"""
        stats = {
            "total_success_queries": sum(len(records) for records in self.success_history.values()),
            "total_failure_queries": sum(len(records) for records in self.failure_history.values()),
            "success_by_type": {},
            "failure_by_type": {},
            "success_rate_by_type": {}
        }
        
        for query_type in QueryType:
            type_key = query_type.value
            success_count = len(self.success_history.get(type_key, []))
            failure_count = len(self.failure_history.get(type_key, []))
            total_count = success_count + failure_count
            
            stats["success_by_type"][type_key] = success_count
            stats["failure_by_type"][type_key] = failure_count
            
            if total_count > 0:
                stats["success_rate_by_type"][type_key] = success_count / total_count
            else:
                stats["success_rate_by_type"][type_key] = 0.0
        
        return stats
    
    # 优化规则实现
    def _add_context_keywords(self, query: str, pattern: QueryPattern) -> str:
        """添加上下文关键词"""
        if "大学" in query or "university" in query.lower():
            return "建议添加具体的学院、系别或项目名称来提高查询精确度"
        return "建议添加相关的上下文关键词"
    
    def _include_institution_name(self, query: str, pattern: QueryPattern) -> str:
        """包含机构名称"""
        return "建议在查询中包含完整的机构或组织名称"
    
    def _use_official_terminology(self, query: str, pattern: QueryPattern) -> str:
        """使用官方术语"""
        return "建议使用官方或正式的术语替代口语化表达"
    
    def _add_ticker_symbol(self, query: str, pattern: QueryPattern) -> str:
        """添加股票代码"""
        return "建议添加公司的股票代码（如AAPL, GOOGL）以提高查询精确度"
    
    def _specify_market(self, query: str, pattern: QueryPattern) -> str:
        """指定市场"""
        return "建议指定具体的股票市场（如NASDAQ, NYSE, 上交所）"
    
    def _add_time_context(self, query: str, pattern: QueryPattern) -> str:
        """添加时间上下文"""
        return "建议添加时间限定（如'最新'、'当前'、'2024年'）"
    
    def _use_financial_terms(self, query: str, pattern: QueryPattern) -> str:
        """使用金融术语"""
        return "建议使用专业的金融术语（如'市值'、'股价'、'交易价格'）"
    
    def _add_entity_context(self, query: str, pattern: QueryPattern) -> str:
        """添加实体上下文"""
        return "建议为提到的实体添加更多描述性信息"
    
    def _clarify_question_scope(self, query: str, pattern: QueryPattern) -> str:
        """明确问题范围"""
        return "建议明确问题的具体范围和边界"
    
    def _include_relevant_keywords(self, query: str, pattern: QueryPattern) -> str:
        """包含相关关键词"""
        return "建议添加与主题相关的专业关键词"
    
    def _add_domain_context(self, query: str, pattern: QueryPattern) -> str:
        """添加领域上下文"""
        return "建议指定具体的技术领域或应用场景"
    
    def _specify_use_case(self, query: str, pattern: QueryPattern) -> str:
        """指定用例"""
        return "建议明确技术的具体应用场景或用例"
    
    def _include_technical_keywords(self, query: str, pattern: QueryPattern) -> str:
        """包含技术关键词"""
        return "建议添加相关的技术术语和专业词汇"
    
    def _clarify_comparison_criteria(self, query: str, pattern: QueryPattern) -> str:
        """明确比较标准"""
        return "建议明确比较的具体标准和维度"
    
    def _specify_entities_clearly(self, query: str, pattern: QueryPattern) -> str:
        """明确指定实体"""
        return "建议清楚地指定要比较的对象或实体"
    
    def _add_context_domain(self, query: str, pattern: QueryPattern) -> str:
        """添加上下文领域"""
        return "建议指定比较的具体领域或上下文"
    
    def _apply_suggestion_to_query(self, query: str, suggestion: str, 
                                 context: Optional[Dict[str, Any]]) -> Optional[str]:
        """将建议应用到查询中"""
        # 基于建议类型实际修改查询
        query_lower = query.lower()
        
        # 添加时间限定
        if "时间限定" in suggestion or "最新" in suggestion:
            if "最新" not in query_lower and "current" not in query_lower:
                return f"{query} 最新"
        
        # 添加股票代码
        if "股票代码" in suggestion or "ticker" in suggestion:
            if context and "companies" in context:
                companies = context["companies"]
                if "apple" in query_lower and "AAPL" not in query:
                    return query.replace("Apple", "Apple (AAPL)")
        
        # 添加具体关键词
        if "具体" in suggestion and "关键词" in suggestion:
            if "iora" in query_lower and "研究所" not in query_lower:
                return query.replace("iora", "IORA研究所")
        
        # 添加上下文信息
        if "上下文" in suggestion and context:
            if "companies" in context:
                companies = context["companies"][:1]  # 取第一个公司
                return f"{query} ({', '.join(companies)})"
        
        return None  # 无法应用建议时返回None
    
    def _create_type_specific_optimizations(self, query: str, query_type: QueryType, 
                                          context: Optional[Dict[str, Any]]) -> List[str]:
        """创建类型特定的优化"""
        optimizations = []
        
        if query_type == QueryType.DEFINITION and "iora" in query.lower():
            optimizations.extend([
                "National University of Singapore IORA meaning",
                "NUS IORA institute operations research analytics", 
                "Singapore university IORA department"
            ])
        elif query_type == QueryType.PRICE and "apple" in query.lower():
            optimizations.extend([
                "AAPL stock price current",
                "Apple Inc AAPL share price latest",
                "Apple company stock market price today"
            ])
        
        return optimizations
    
    def _create_historical_variations(self, query: str, query_type: QueryType) -> List[str]:
        """基于历史创建查询变体"""
        variations = []
        
        type_key = query_type.value
        if type_key in self.success_history:
            # 分析成功查询的模式
            successful_queries = self.success_history[type_key][-10:]  # 最近10个成功查询
            
            # 提取常见的成功模式
            for record in successful_queries:
                successful_query = record["query"]
                if self._queries_similar(query, successful_query):
                    variations.append(successful_query)
        
        return variations[:2]  # 最多2个历史变体
    
    def _queries_similar(self, query1: str, query2: str) -> bool:
        """判断两个查询是否相似"""
        words1 = set(query1.lower().split())
        words2 = set(query2.lower().split())
        
        # 简单的相似度计算
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        if len(union) == 0:
            return False
        
        similarity = len(intersection) / len(union)
        return similarity > 0.3  # 30%以上相似度
    
    def _generate_context_based_suggestions(self, query: str, context: Dict[str, Any]) -> List[str]:
        """基于上下文生成建议"""
        suggestions = []
        
        # 如果上下文中有价格信息，建议使用
        if "price" in str(context).lower() or "cost" in str(context).lower():
            suggestions.append("可以引用之前获取的价格信息进行更精确的查询")
        
        # 如果上下文中有公司信息，建议使用
        if any(term in str(context).lower() for term in ["company", "corp", "inc", "ltd"]):
            suggestions.append("建议使用上下文中提到的具体公司信息")
        
        return suggestions
    
    def _get_historical_suggestions(self, query: str, query_type: QueryType) -> List[str]:
        """获取基于历史的建议"""
        suggestions = []
        
        type_key = query_type.value
        
        # 分析失败查询的模式
        if type_key in self.failure_history:
            failure_patterns = self._analyze_failure_patterns(self.failure_history[type_key])
            for pattern in failure_patterns:
                suggestions.append(f"避免使用过于{pattern}的表达方式")
        
        return suggestions
    
    def _analyze_failure_patterns(self, failure_records: List[Dict]) -> List[str]:
        """分析失败模式"""
        patterns = []
        
        # 分析失败查询的共同特征
        short_queries = sum(1 for record in failure_records if record["query_length"] <= 3)
        total_queries = len(failure_records)
        
        if total_queries > 0:
            if short_queries / total_queries > 0.5:
                patterns.append("简短")
        
        return patterns
    
    def _get_historical_success_rate(self, query_type: QueryType) -> float:
        """获取历史成功率"""
        type_key = query_type.value
        
        success_count = len(self.success_history.get(type_key, []))
        failure_count = len(self.failure_history.get(type_key, []))
        total_count = success_count + failure_count
        
        if total_count == 0:
            return 0.5  # 默认成功率
        
        return success_count / total_count