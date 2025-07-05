# **Google Gemini 2.5 系列模型使用指南**

## **模型概述与区别**

**Gemini 2.5 Pro**：定位于最高性能的“大模型”，默认开启“思考 (thinking)”模式，擅长复杂推理、代码生成和多模态理解  。它可以处理音频、图像、视频、文本甚至 PDF 作为输入，输出文本结果 。Gemini 2.5 Pro 拥有极高的上下文窗口（输入最长 *~*1,048,576 tokens，输出最长 65,536 tokens） 。适用于复杂代码/数学问题求解、大型数据集分析等场景 。由于引入“思考”能力，模型在回答前会进行多步推理，从而提升准确性和推理深度 。

**Gemini 2.5 Flash**：在性能和成本间取得平衡的通用模型，默认也支持思考模式  。支持多模态输入 (文本、图像、视频、音频) 并输出文本 。上下文窗口同样高达约1,048,576个token输入和65,536个token输出 。相较Pro，Flash成本更低、延迟更低，非常适合大规模、低延迟、高吞吐的任务，以及需要一定推理能力的 Agent 场景 。例如批量内容生成、分类、对话等，在保证较高智能的同时降低成本。

**Gemini 2.5 Flash-Lite**：2.5系列中新推出的**预览版**轻量模型，优化为最低延迟和最低成本  。支持多模态输入（文本、图像、视频、音频）和文本输出 。上下文窗口约1,000,000个token输入，输出上限64,000 token 。Flash-Lite的特点是**高吞吐、低成本**，非常适合对响应速度和调用成本要求极高的场景，例如实时对话、文本分类、海量请求的服务等  。相较Flash，Flash-Lite在推理深度上略有下降，但仍支持基本的推理和工具使用能力。

下表总结了三种模型的主要区别：

| **模型**             | **输入/输出格式**                  | **上下文窗口（输入/输出）** | **特性概述**                                                 |
| -------------------- | ---------------------------------- | --------------------------- | ------------------------------------------------------------ |
| **Gemini 2.5 Pro**   | 文本、图像、音频、视频、PDF → 文本 | ~1,048,576 / 65,536 tokens  | 最高智能，“思考”能力强，适合复杂推理、长文档分析             |
| **Gemini 2.5 Flash** | 文本、图像、音频、视频 → 文本      | ~1,048,576 / 65,536 tokens  | 性能-成本平衡，低延迟高吞吐，也支持思考和工具调用            |
| **2.5 Flash-Lite**   | 文本、图像、音频、视频 → 文本      | ~1,000,000 / 64,000 tokens  | 最低成本，低延迟高并发，适合实时/海量简答任务（2.5系列预览版） |

*注：以上token上限为模型支持的理论最大上下文长度，并非每次调用都建议填满。实际最大有效上下文可能受请求大小限制。*

## **调用方式：REST API 与 Python SDK**

**REST API 调用**：Gemini 提供 RESTful 接口，可通过HTTP请求调用模型。基础URL为 https://generativelanguage.googleapis.com/v1beta/，使用对应模型的路径和方法。例如，调用 gemini-2.5-flash 模型的文本生成接口（generateContent），可使用如下 curl 命令：

```
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "contents": [{
          "parts": [ { "text": "列出三条常见的烘焙饼干食谱。" } ]
        }],
        "generationConfig": {
          "temperature": 0.7,
          "maxOutputTokens": 1024
        }
      }'
```

上述请求通过在URL中指定模型名称和方法，并在HTTP头中提供API密钥（x-goog-api-key） 。请求体为JSON，包括contents字段（提示内容）以及可选的generationConfig参数（如温度、输出长度限制等）。REST API 会返回包含模型回答的JSON响应，比如candidates列表，其中包含生成的文本等数据。对于聊天模型（支持多轮对话），也可以使用 :generateMessage 端点并按照聊天消息格式提供 prompt 。REST 接口支持的功能非常全面，如批量文本嵌入、函数调用等均通过不同路径实现（详见官方 API 参考）。

**Python SDK 调用**：Google 提供了官方的 **Google GenAI SDK**（新版 SDK，替代旧版 google-generativeai）用于简化 Gemini API 的调用 。可通过 pip install google-genai 安装最新版 SDK 。使用SDK前，需要获取 Gemini API Key 并设置认证（例如将API Key配置为环境变量）。基本使用示例如下：

```
from google import genai
from google.genai import types

# 使用 API Key 调用（Gemini Developer API）
client = genai.Client(api_key="你的_GEMINI_API_KEY")  # 或提前设置 GOOGLE_API_KEY 环境变量 [oai_citation:32‡pypi.org](https://pypi.org/project/google-genai/#:~:text=Gemini%20Developer%20API%3A%20Set%20,as%20shown%20below) [oai_citation:33‡pypi.org](https://pypi.org/project/google-genai/#:~:text=client%20%3D%20genai)

# 调用文本生成
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="北京的天气如何？",
    # 可选参数：如温度、最大输出 Token 数等
    config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=512)
)
print(response.text)  # 输出模型回复文本
```

如上，使用 genai.Client 创建客户端实例。对于 Gemini 开发者API，直接提供 api_key 即可 ；若使用 Google Cloud Vertex AI 路径，则需指定 vertexai=True 和 GCP 项目、区域等参数 。然后通过 client.models.generate_content 调用指定模型生成文本 。contents 参数可以直接传入字符串或消息列表，SDK会负责序列化为API所需格式。response 对象包括生成结果文本，可通过 response.text 获取主要回答内容 。



*提示*：若将API密钥设置为环境变量（如 GEMINI_API_KEY 或 GOOGLE_API_KEY），SDK 会自动读取使用  。也可通过 genai.Client() 的参数传入。不提供密钥则需要在请求时明确指定。SDK 默认使用 v1beta 版本的接口，可通过 http_options=types.HttpOptions(api_version="v1") 切换到稳定版v1 。



**其他语言 SDK**：除了 Python，官方还提供 JavaScript/TypeScript（@google/genai）、Go（google.golang.org/genai）、Java 等版本 SDK 。调用方式与Python类似。在不使用官方SDK时，也可直接通过HTTP请求（REST API）或社区库调用。Google 建议优先使用新版 GenAI SDK，以支持最新特性 。

## **速率限制与上下文缓存**

**默认速率限制**：Gemini API 对不同模型的调用频率和配额有默认限制。下表为 **未升级账号（Free Tier）** 时各模型的限制 ：

| **模型**              | **每分钟请求数 (RPM)** | **每日请求数 (RPD)** | **每分钟输入Token数 (TPM)** |
| --------------------- | ---------------------- | -------------------- | --------------------------- |
| Gemini 2.5 Pro        | 5 次/min               | 100 次/天            | 250,000 tokens/min          |
| Gemini 2.5 Flash      | 10 次/min              | 250 次/天            | 250,000 tokens/min          |
| Gemini 2.5 Flash-Lite | 15 次/min              | 1,000 次/天          | 250,000 tokens/min          |

可以看到，Flash-Lite 在免费配额下允许更高的并发和每日请求次数，非常适合测试高并发场景。**提升速率**：如果需要更高配额，可以申请升级到更高的付费等级 (Tier 1/2/3)。例如，升级后2.5 Pro最高可达150 RPM (Tier1) 甚至2000 RPM (Tier3)，2.5 Flash 可升至1000 RPM (Tier1) / 10000 RPM (Tier3) 等  。Token吞吐率和并发限制也相应提高。但需要注意，实际吞吐可能受模型性能和网络影响，上述数值为平台上限 。

**上下文缓存 (Context Caching)**：Gemini 引入了上下文缓存机制，用于在多次请求之间重用大量不变的上下文，从而 **节省重复输入的 Token 成本**。适用于“有大段共同上下文、多次查询不同细节”的场景，如对同一长文档反复提问 。使用上下文缓存的大致流程为：首先通过 **缓存接口** 上传或指定需要缓存的上下文内容，获得一个 cached_content 标识；之后的生成请求可以引用该缓存ID，模型会在回答时自动将缓存内容作为上下文加入  。这样开发者无需每次都提交相同的大文本，减少带宽和计费。

上下文缓存有如下要点：

- **最小缓存长度**：为保证收益，只有上下文内容超过一定长度才允许缓存。2.5 Flash / Flash-Lite 模型最少需要 **1024** 个token 才可缓存，2.5 Pro 则需 **2048** token 起步  。
- **Token计费**：缓存内容本身的Token以**优惠价**计费（约为正常输入Token价格的1/4），使用缓存回答时，这部分Token不重复按普通输入收费  。例如2.5 Pro缓存Token每百万收费约$0.3125，对应正常输入价的25% 。每小时还对持续保留的缓存收取少量存储费（约$4.50/百万Token/小时，Flash系列为$1.00/百万/小时）  。缓存命中后，后续请求仅对新增的提问和模型输出部分按正常价计费。
- **使用限制**：上下文缓存目前不受额外速率限制，遵循模型普通请求的配额 。缓存内容的有效期可设置TTL，超过时间可自动过期。也可手动管理缓存的创建、获取和删除  。请注意缓存的内容Token也计入单次请求的上下文长度上限 。

通过上下文缓存，开发者可以高效地进行长篇文档问答、多轮摘要等操作：先上传长文档到缓存，然后多轮对话每次仅发送问题及引用缓存ID，即可让模型基于该文档回答，且重复部分的Token开销显著降低。

## **功能特性：结构化输出、函数调用和嵌入**

### **结构化输出（JSON模式）**

Gemini 模型可以直接生成**结构化结果**，支持 JSON 格式输出或枚举值输出 。这在信息抽取、工具集成等需要标准格式的场景非常有用。开发者有两种方式启用JSON输出：

- **响应模式配置 Schema（推荐）**：通过请求配置 response_schema 和 response_mime_type="application/json"，预先约束模型只产出符合给定模式的JSON  。这种方式模型不会输出额外解释，只返回JSON，可靠性高。
- **提示词中说明格式**：在prompt中用说明要求模型以JSON格式回答。这种方式简单但不如直接配置Schema稳定。

使用Python SDK，可以结合数据模型（例如 Pydantic）来定义JSON模式，然后传给SDK配置。例如：我们希望模型返回饼干食谱的列表，每个食谱包含名称和原料列表：

```
from google import genai
from pydantic import BaseModel

class Recipe(BaseModel):
    recipe_name: str
    ingredients: list[str]

client = genai.Client(api_key="你的_API_Key")
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="列出几种常见的曲奇饼干食谱，并包含各自需要的原料。",
    config={
        "response_mime_type": "application/json",
        "response_schema": list[Recipe],  # 定义预期输出为 Recipe 列表
    },
)
print(response.text)   # JSON字符串输出
recipes: list[Recipe] = response.parsed  # 直接得到 Pydantic 解析后的对象列表
```

如上，通过 response_schema 提供 Recipe 数据模型的列表类型，模型将严格按照该结构返回JSON  。我们可以直接使用 response.parsed 获取解析后的 Python 对象列表（需注意当前SDK对 Pydantic validator 的支持有限，复杂校验下 parsed 可能为空 ）。

使用REST API时，可在JSON请求的 generationConfig 中加入类似的 schema 定义 。模型会返回符合schema的JSON文本，可解析后处理。

### **函数调用（Function Calling / Tool Use）**

Gemini 模型支持 OpenAI 类似的**函数调用**能力，可以依据提示要求，返回需要调用的函数及参数，让开发者执行后再将结果反馈给模型。借助函数调用，模型可动态使用外部工具（如查数据库、调用API、执行代码等），从而构建更强大的 Agent 系统 。

**函数描述声明**：开发者需要先定义允许模型调用的函数列表，包括函数名称、功能说明、参数schema等。SDK提供了辅助方法将现有Python函数自动转换为声明，例如：

```
from google.genai import types

def multiply(a: float, b: float):
    """Returns a * b."""
    return a * b

fn_decl = types.FunctionDeclaration.from_callable(callable=multiply, client=client)
print(fn_decl.to_json_dict())  # 查看自动推断的函数schema
```

上述代码将Python函数签名转换为 Gemini 可用的函数描述 。当然也可以手工创建 FunctionDeclaration 对象指定所需的函数接口。准备好函数列表后，通过请求配置 tools=[FunctionDeclaration对象列表] 来注册这些可用函数 。还可以使用 FunctionCallingConfig 设置函数调用模式，例如mode="AUTO"（模型自主决定是否调用函数）或"NONE"（禁止函数调用）、"ANY"（强制将回复作为函数调用返回）等 。默认是AUTO模式，模型会根据提示自动决定回答还是函数调用 。

**函数调用流程**：当函数调用被启用且模型判断需要调用外部函数时，它不会直接给出最终答案，而是返回一个包含 function_call 字段的回答，指明所要调用的函数名和参数 。在Python SDK中，response.function_calls 列表可获取模型建议的所有函数调用 。开发者拿到函数名和参数后，应在自己程序中执行相应函数，将执行结果再通过后续对话消息反馈给模型。Gemini SDK 提供了 chat 会话管理，可以持续与同一模型对话（见下文），这样在下一次 chat.send_message() 时附带函数执行结果，模型即可利用结果继续完整回答。

**示例**：假设我们提供了一个 get_current_time() 函数给模型，当用户问“现在几点”，模型可能返回一个 function_call 建议调用 get_current_time。我们执行后获取时间，再把时间结果发给模型，最后模型回答给用户。整个流程可以由LangChain等agent框架或手写逻辑实现。

**工具集成**：函数调用实际上是一种通用工具调用机制。Gemini 2.5 Flash/Pro 还内置了一些**原生工具**：“Search Grounding”允许模型直接发起Google搜索查询以获取实时信息 ，“Code Execution”允许模型执行Python代码片段并获取结果 。这些工具的使用也通过函数调用/工具接口来配置。例如，在请求的 tools 列表里加入 {'google_search': {}} 或 {'code_execution': {}} 来启用（需使用 Live API WebSocket 模式） 。模型在需要时会自动调用这些工具，并将结果纳入思考链条。开发者还可以通过 **MCP（Model Context Protocol）** 与自定义后端工具对接，Gemini SDK 对 MCP 有内置支持，可自动执行模型发起的 MCP 调用并循环反馈  。

**Streaming（流式响应）**：Gemini 支持流式返回模型输出，便于边生成边呈现长文本。REST API可通过设置 stream=true（若支持）或使用Live API获取连续消息流。Python SDK 则提供了 *streaming* 接口：如 chat.send_message_stream(prompt) 将返回一个生成内容片段 (chunk) 的迭代器 。示例：

```
chat = client.chats.create(model='gemini-2.5-flash')
for chunk in chat.send_message_stream("给我讲一个故事吧："):
    print(chunk.text, end="", flush=True)
```

上述代码会逐步打印模型输出的故事文本，实现流式输出 。Streaming 对于降低延迟、提供更好交互体验很有帮助。需注意控制台逐块打印时需要处理好结尾换行和flush。

### **嵌入生成（Embeddings）**

Gemini 提供专门的**文本嵌入模型**用于获取文本的向量表示，以支持语义搜索、聚类、分类等任务 。嵌入模型与聊天/生成模型分离，调用方法和OpenAI Embedding类似。目前主要有三种嵌入模型可用 ：

- **gemini-embedding-exp-03-07**：Gemini系列的实验版嵌入模型（2025年3月7日版本）。支持 **8000 tokens** 长文本输入，输出 **3072 维** 的向量 。这是目前维度最高、效果最强的Embedding模型，但向量存储和计算成本也较高 。模型采用“套娃表示学习 (Matryoshka Representation)”技术，支持无损地截断向量维度，以便在略微降低精度的前提下节省存储 。开发者可按需将3072维向量截断为2048、1024、512等维度使用 。
- **text-embedding-004**：稍早版本的通用Embedding模型，支持约3000 tokens输入，输出 **768 维** 向量 。可用于大多数常规NLPEmbedding任务，速度快、维度适中，适合对存储要求较高的应用。
- **embedding-001**：更旧的Embedding模型，输出 **768维** 向量，性能和多样性略低于004版本，一般建议使用更新模型 。

**调用方法**：使用Python SDK，可以通过 client.models.embed_content 方法获取文本嵌入向量 。例如：

```
# 单条文本求 embedding
response = client.models.embed_content(
    model='gemini-embedding-exp-03-07',
    contents='天空为什么是蓝色？'
)
vec = response.embeddings[0]  # 得到第一个文本的向量表示

# 多条文本一起请求，并截断输出维度为1024
response = client.models.embed_content(
    model='gemini-embedding-exp-03-07',
    contents=['天空为什么是蓝色？', '你几岁了？'],
    config=types.EmbedContentConfig(output_dimensionality=1024)
)
vecs = response.embeddings  # 将返回两个1024维向量
```

如上，contents 可以是字符串或字符串列表。response.embeddings 则包含对应的向量（Python SDK 会封装为数组或张量，直接打印 response 也可看到向量内容）  。示例中还展示了通过 EmbedContentConfig(output_dimensionality=N) 可让模型自动截断向量维度为N（需<=模型最大维度），利用Matryoshka特性在服务端完成降维 。REST API 调用嵌入时，对应的端点是 :embedText 或 :embedContent，请求体提供文本列表，响应会返回一个 embedding 数组。同一次请求可发送多条文本获取批量向量。



**Embedding 用例**：得到文本向量后，可将其存入向量数据库用于相似度搜索（官方提供了向量库教程 ），或结合余弦相似度等计算文本相似性、语义聚类等。需注意，Gemini embedding 默认不保证跨语言对齐，如果需要多语言Embedding或特定领域优化，可关注后续模型更新或fine-tuning能力。

### **Token 统计与费用估算**

在使用大模型时，**准确地计算Token数量**有助于控制上下文长度和预估费用。Gemini SDK 提供了便捷的 Token 计数功能。开发者可以使用 client.models.count_tokens 来统计一段内容在指定模型下会被分成多少Token ：

```
result = client.models.count_tokens(
    model='gemini-2.5-pro',
    contents="Hello, world! 你好，世界！"
)
print(result)  # 输出类似：{"tokenCount": X} 或直接输出数值
```

上述调用会返回该内容在模型分词器下的Token计数 。这对长文档裁剪、确保不超上下文窗口很有帮助。请注意，不同模型可能使用不同词表，但Gemini 2.x系列模型基本通用分词规则。



**Token 计费规则**：Gemini API 的计费以 **百万 token** 为单位定价，不区分Prompt和Completion数量级时则按总token计费（某些模型对输入输出分开定价，见下文）。**具体计费**：每个请求费用 = 输入token数量 * 输入单价 + 输出token数量 * 输出单价 + 其它附加费用（如思考token、缓存token、工具调用等）。其中“思考/推理”过程产生的中间token（例如模型在内部Chain-of-thought的token）也计入输出token并收费，但这些思考内容通常不会返回给用户，只体现在计费的 usage metadata 上 。Google 会在响应中给出 usage 字段，包括 promptTokens 和 responseTokens，可用于记录每次请求实际使用token数。

## **定价与成本比较**

Gemini API 按使用量付费，不同模型及不同功能的单价有所差异。定价单位通常为每 **100 万 tokens** 的费用（按输入或输出分别计算），某些多模态功能按请求计费。以下列出 2.5 Pro、Flash、Flash-Lite 三个文本模型的主要计费标准（以 **美元/$** 为单位）：

- **Gemini 2.5 Pro**：输入token约 $1.25/百万；输出token约 $10/百万 。若单次提示超过200k token的超长prompt，则超出部分成本翻倍（输入$2.50，输出$15/百万）  。上下文缓存中的token按 ~$0.31/百万 计费（若prompt≤200k） 。例如，发送1000个token的提问并获得1000个token的回答，费用约为(1000/1e6*$1.25 + 1000/1e6*$10) ≈ $0.0113。
- **Gemini 2.5 Flash**：输入token约 $0.30/百万；输出token约 $2.50/百万 。（Flash未明确区分prompt阈值，默认上下文长度内按统一单价计费）。相比Pro，Flash的单token费用约为Pro的1/4  。上下文缓存token价约 $0.075/百万，为普通输入的1/4 。因此Flash非常适合大量中短文本的处理，性价比高。
- **Gemini 2.5 Flash-Lite**：输入token约 $0.10/百万；输出token约 $0.40/百万 。这是2.5系列成本最低的模型，大致为Flash费用的1/3～1/6。上下文缓存token价约 $0.025/百万 。低成本意味着对于简短回答或批量请求，Flash-Lite能大幅节省费用。例如1000 token输入+1000 token输出仅约 $0.0005，适合海量调用的场景。

除了上述纯文本Token费用，**多模态**调用和特殊功能可能有额外费用：如语音合成输出约 $12/百万tokens，相当于每秒音频 ~$0.012（8k token≈1秒音频）  ；图片生成每张约$0.039（对应1290 token输出） ；使用Google网络搜索工具在免费配额外每1000次收费$35 ；Live API（实时对话流）调用也有单独定价 。模型Fine-tuning调优目前按照相同的token价格计费，不另收模型训练费用 。

*提示*：在API响应或SDK的 response 对象中，可以获取 usage_metadata 或 usage 信息，了解此次请求的实际 token 使用量及估算费用，以便进行成本监控和优化 。另外，在Google Cloud控制台的计费页面可以查看累计用量，每月会根据用量结算费用 。

## **Agent 集成与多轮对话支持**

Gemini 系列模型为构建自主Agent和多轮对话系统提供了全面支持：

- **多轮对话与记忆**：模型可以通过**上下文消息**维持对话记忆。使用 Python SDK 时，可以创建一个 chat = client.chats.create(model=...) 对象 。随后多次调用 chat.send_message("...") 即可在同一对话线程中连续交流 。模型会自动参考之前消息，理解上下文。如下示例：

```
chat = client.chats.create(model='gemini-2.5-flash')
res1 = chat.send_message("帮我讲一个简短的故事。")
print(res1.text)  # 模型返回一个故事
res2 = chat.send_message("请用一句话总结这个故事")
print(res2.text)  # 模型会记住上一步的故事内容并给出总结
```

- 在上述第二次提问时模型并未重复故事，而是利用“记忆”直接总结  。开发者也可以显式地在每次请求里传入之前对话（若不使用SDK会话对象时），Gemini接口支持以 messages 列表或 contents 列表形式提交多条消息，模型会按顺序理解。**内存管理**方面，如果对话很长接近上下文窗口极限，可能需要对旧消息进行摘要或移除一部分（Gemini的百万级上下文窗口使得大部分对话无需清理即可持续较多轮）。另外，结合**Context Caching**，可以在多轮对话开始时预置大量背景资料（如长文档）为隐含上下文，模型每轮都会参考 。
- **“思考”模式**：2.5 Pro和Flash默认开启了“思考 (Thinking)”能力 。这意味着模型在产生最终回答前，可能先进行多步推理、工具调用等内部步骤。这些步骤及结果有时会通过 function_call 或中间消息形式暴露给开发者，但大部分时候自动完成，不需要人工干预。**思考Token**会计入输出，但不会显示给最终用户（除非显式要求输出思考过程） 。思考模式使模型在Agent场景下表现更出色，能够**自行决定**何时调用工具或拆解问题 。开发者也可以通过参数控制思考深度，例如限制“思考预算”等（Gemini提供选项配置模型最多思考多少步或多少Token）  。
- **工具调用与Agent**：正如前文函数调用部分所述，Gemini模型可以无缝衔接**外部工具**。借助函数调用接口，模型可以请求使用开发者提供的函数（数据库查询等），或使用内置搜索、代码执行等能力  。Google 将这些能力与对话结合，定位于“Agentic AI”时代  。例如，利用Gemini 2.5 Flash结合LangChain或LangGraph框架，可以构建能读取企业文档、调用API、执行计算的智能Agent 。实践中，可将需要的工具函数声明传给模型，让模型在对话中**主动**选择调用。当模型返回function_call时，Agent执行之并再把结果回复模型，模型即可据此给出最终答案或进一步行动。这一循环可以持续进行多轮，直到模型给出自然语言回答。Gemini SDK 对此流程提供了一定支持（如前述 tools=[session] MCP自动循环执行工具，或在 Live API 中由 SDK 自动代为调用工具再回复模型 ），使 Agent 开发更便利。
- **流式对话 (Streaming)**：对于实时性要求高的应用（如AI助理实时回答、语音对话），Gemini 提供了 **Live API**（WebSocket流式接口） 。通过Live API，模型可以一边思考/调用工具，一边逐步将回复发送给客户端，实现互动式对话。Gemini 2.5 Flash 支持Live API，并有专门的 Flash Live 模型 variant 用于低延迟双向交流 。在Python SDK中，Live API可通过异步接口使用（例如 await chat.send_message_stream() 或底层 websocket 客户端）。另外，如果需要语音输入输出的多模态对话，Gemini 还提供 **Native Audio** 对话模型，可直接接受音频并返回语音/文字，同时支持思考模式  。这对于构建语音助理、客服机器人的Agent非常强大。需要注意的是，使用Live API和语音对话可能需要在云端开通相应功能，且收费标准与纯文本不同（见上文定价）。

总而言之，Gemini 2.5 系列为构建复杂对话系统和Agent提供了一站式支持：超大的上下文窗口可以引入海量知识，思考+函数调用赋予工具使用和分步推理能力，结构化输出方便与程序逻辑衔接，流式交互保障了用户体验。开发者可以从官方提供的**示例代码**和**Notebook**（如 Gemini Cookbook 中的LangChain集成示例）入手，将这些功能组合应用于自己的Python工程项目，快速打造出强大的智能应用 。

## **Python 使用示例汇总**

下面汇总几个常见功能的 Python 代码示例，便于工程师参考：

- **文本生成（对话）**：

```
from google import genai
client = genai.Client(api_key="YOUR_API_KEY")
chat = client.chats.create(model="gemini-2.5-flash")
res = chat.send_message("你好！你是谁？")
print(res.text)  # 输出模型的回复文本
```

- 借助 SDK 的 chat 会话，可以轻松实现多轮对话 。第一次提问后，可继续调用 chat.send_message("<续问>") 保持上下文。
- **流式响应**：

```
chat = client.chats.create(model="gemini-2.5-flash")
for chunk in chat.send_message_stream("请逐字母拼出 'HELLO'："):
    print(chunk.text, end="")
# 模型会逐步输出 H E L L O，每个 chunk 可能是部分文本
```

- 如上，通过迭代 send_message_stream 的结果来获取逐步输出 。对于长文本回答，这种方式可以边生成边处理。
- **结构化JSON输出**：

```
from google.genai import types
schema = {
  "type": types.Type.OBJECT,
  "properties": {
    "名字": {"type": types.Type.STRING},
    "年龄": {"type": types.Type.INTEGER}
  }
}
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="提供一个示例：名字为张三，年龄为 25。",
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema
    )
)
print(response.text)  # e.g. {"名字": "张三", "年龄": 25}
```

- 这里直接用字典构建了一个schema（等价于定义了包含名字和年龄的JSON结构），模型将返回匹配该schema的JSON  。通过这种方式，可以确保输出易于机器解析。
- **函数调用**：

```
from math import factorial
from google.genai import types
# 定义一个用于计算阶乘的工具函数
def get_factorial(n: int) -> int:
    """返回 n 的阶乘"""
    return factorial(n)
fn = types.FunctionDeclaration.from_callable(get_factorial, client=client)
prompt = "计算 5! 等于多少？请调用工具计算而不是自己算。"
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(tools=[fn])
)
# 模型此时可能返回一个函数调用建议，而不是直接给出答案
func_calls = response.function_calls
if func_calls:
    name = func_calls[0].name  # 应为 "get_factorial"
    args = func_calls[0].args  # 如 {"n": 5}
    result = get_factorial(**args)  # 调用本地函数得到结果
    follow_up = f"{name} 函数返回的结果是 {result}。"
    final = chat.send_message(follow_up)  # 将结果反馈给模型
    print(final.text)  # 模型最终回答，例如 "5! 等于 120。"
```



- 上述逻辑展示了函数调用的基本流程：模型先请求使用函数，我们执行后告知结果，模型再给出最后答案。实际开发中可用 loop 自动处理所有 function_calls。Gemini SDK 和 Agent 框架能简化这一过程，但理解底层机制有助于调试 。
- **嵌入向量**：



```
texts = ["人工智能", "机器 学习", "深度学习"]
resp = client.models.embed_content(model="text-embedding-004", contents=texts)
vectors = resp.embeddings  # 得到3个768维向量
# 计算第1和第2个文本向量的余弦相似度
import numpy as np
v1, v2 = np.array(vectors[0]), np.array(vectors[1])
cosine_sim = np.dot(v1, v2) / (np.linalg.norm(v1)*np.linalg.norm(v2))
print("相似度:", cosine_sim)
```



- 通过 embed_content 获取文本embedding 后，可以进行向量相似度计算等操作。上例简单计算了“人工智能”和“机器 学习”的语义相似度。
- **Token 计数**：



```
txt = "这是一个测试文本。This is a test."
result = client.models.count_tokens(model="gemini-2.5-pro", contents=txt)
print(f"Token 数量: {result['tokenCount']}")
```



- 利用 count_tokens 可以方便地得知任意字符串在指定模型下的分词数量 。这有助于在提交请求前检查长度是否超限，以及预估费用。





以上示例覆盖了文本生成、多轮对话、流式输出、JSON结构化、函数调用、文本嵌入、token计数等常用功能，开发者可根据自身应用需求进行组合。在实际工程中，建议充分参考 **Google 官方文档**  和 **Gemini API Cookbook** 来了解更多细节和最佳实践。例如，如何进行**长文档摘要**、如何使用**文件上传接口**提供PDF给模型分析  ，如何利用**LangChain**集成Gemini模型等 。凭借Gemini 2.5系列强大的能力，开发者可以在Python中高效构建出功能丰富的智能应用。



**参考文献**：



1. Google AI Developers – *Gemini 2.5 模型概览*  
2. Google AI Developers – *Gemini 2.5 Flash/Flash-Lite 介绍*  
3. Google AI Developers – *Gemini 模型能力列表*  
4. Google Cloud Blog – *Gemini 2.5 Flash-Lite 性能与应用* 
5. Gemini API 文档 – *速率限制 Rate Limits*  
6. Gemini API 文档 – *上下文缓存 Context Caching*  
7. Gemini API 文档 – *结构化输出 (JSON Schema)*  
8. Gemini API 文档 – *函数调用 Function Calling*  
9. Gemini API 文档 – *嵌入模型 Embeddings*  
10. Gemini API 文档 – *定价 Pricing*  
11. Gemini API 文档 – *Python SDK 使用*  
12. Gemini API Cookbook – *示例代码*  