# Browser Use MCP Server - 内置Prompt指南

## 🌐 服务概述
基于browser-use的AI浏览器自动化服务，提供26个完整的浏览器操作工具。

## 🔧 工具分类与使用指南

### 🧭 导航控制
- **browser_navigate**: 导航到指定URL
  - 参数: `url` (required) - 要访问的URL地址
  - 示例: `<browser_use><browser_navigate>https://www.google.com</browser_navigate></browser_use>`

- **browser_go_back**: 返回上一页
  - 参数: 无
  - 示例: `<browser_use><browser_go_back></browser_go_back></browser_use>`

### 🖱️ 页面交互
- **browser_click_element**: 点击页面元素
  - 参数: `index` (required) - 要点击的元素索引
  - 示例: `<browser_use><browser_click_element>5</browser_click_element></browser_use>`

- **browser_input_text**: 在表单中输入文本
  - 参数: `index` (required), `text` (required)
  - 示例: `<browser_use><browser_input_text>{"index": 2, "text": "hello world"}</browser_input_text></browser_use>`

- **browser_send_keys**: 发送键盘按键
  - 参数: `keys` (required) - 如Enter、Escape、Control+c等
  - 示例: `<browser_use><browser_send_keys>Enter</browser_send_keys></browser_use>`

### 📄 内容操作
- **browser_search_google**: Google搜索
  - 参数: `query` (required) - 搜索查询词
  - 示例: `<browser_use><browser_search_google>Python machine learning tutorial</browser_search_google></browser_use>`

- **browser_extract_content**: 提取页面内容
  - 参数: `goal` (required), `include_links` (optional)
  - 示例: `<browser_use><browser_extract_content>extract all product information</browser_extract_content></browser_use>`

- **browser_screenshot**: 截取页面截图
  - 参数: `filename` (optional) - 截图文件名
  - 示例: `<browser_use><browser_screenshot>current_page.png</browser_screenshot></browser_use>`

- **browser_save_pdf**: 保存页面为PDF
  - 参数: 无
  - 示例: `<browser_use><browser_save_pdf></browser_save_pdf></browser_use>`

### 📋 表单处理
- **browser_get_dropdown_options**: 获取下拉菜单选项
  - 参数: `index` (required) - 下拉菜单元素索引
  - 示例: `<browser_use><browser_get_dropdown_options>3</browser_get_dropdown_options></browser_use>`

- **browser_select_dropdown_option**: 选择下拉菜单选项
  - 参数: `index` (required), `text` (required)
  - 示例: `<browser_use><browser_select_dropdown_option>{"index": 3, "text": "Option 1"}</browser_select_dropdown_option></browser_use>`

### 📜 滚动操作
- **browser_scroll_down**: 向下滚动
  - 参数: `amount` (optional) - 滚动像素数
  - 示例: `<browser_use><browser_scroll_down>500</browser_scroll_down></browser_use>`

- **browser_scroll_up**: 向上滚动
  - 参数: `amount` (optional) - 滚动像素数
  - 示例: `<browser_use><browser_scroll_up>300</browser_scroll_up></browser_use>`

- **browser_scroll_to_text**: 滚动到指定文本
  - 参数: `text` (required) - 要滚动到的文本内容
  - 示例: `<browser_use><browser_scroll_to_text>Sign up</browser_scroll_to_text></browser_use>`

### 🏷️ 标签管理
- **browser_open_tab**: 打开新标签
  - 参数: `url` (required) - 要在新标签中打开的URL
  - 示例: `<browser_use><browser_open_tab>https://www.example.com</browser_open_tab></browser_use>`

- **browser_close_tab**: 关闭标签
  - 参数: `page_id` (required) - 要关闭的标签ID
  - 示例: `<browser_use><browser_close_tab>1</browser_close_tab></browser_use>`

- **browser_switch_tab**: 切换标签
  - 参数: `page_id` (required) - 要切换到的标签ID
  - 示例: `<browser_use><browser_switch_tab>0</browser_switch_tab></browser_use>`

### 🔍 页面分析
- **browser_get_ax_tree**: 获取页面可访问性树
  - 参数: `number_of_elements` (required) - 返回的元素数量
  - 示例: `<browser_use><browser_get_ax_tree>50</browser_get_ax_tree></browser_use>`

- **browser_get_page_info**: 获取页面信息
  - 参数: 无
  - 示例: `<browser_use><browser_get_page_info></browser_get_page_info></browser_use>`

- **browser_get_current_url**: 获取当前URL
  - 参数: 无
  - 示例: `<browser_use><browser_get_current_url></browser_get_current_url></browser_use>`

### ⚡ 高级功能
- **browser_drag_drop**: 拖拽操作
  - 参数: `element_source` (optional), `element_target` (optional), 坐标参数 (optional)
  - 示例: `<browser_use><browser_drag_drop>{"element_source": ".item1", "element_target": ".dropzone"}</browser_drag_drop></browser_use>`

- **browser_use_execute_task**: AI任务执行
  - 参数: `task` (required), `max_steps` (optional), `use_vision` (optional)
  - 示例: `<browser_use><browser_use_execute_task>Search for Python tutorials and open the first result</browser_use_execute_task></browser_use>`

### ⏱️ 流程控制
- **browser_wait**: 等待指定时间
  - 参数: `seconds` (optional) - 等待的秒数，默认3
  - 示例: `<browser_use><browser_wait>5</browser_wait></browser_use>`

- **browser_done**: 标记任务完成
  - 参数: `text` (required), `success` (required)
  - 示例: `<browser_use><browser_done>{"text": "Task completed", "success": true}</browser_done></browser_use>`

- **browser_close_session**: 关闭浏览器会话
  - 参数: 无
  - 示例: `<browser_use><browser_close_session></browser_close_session></browser_use>`

## 💡 最佳实践

1. **搜索流程**: 使用`browser_search_google` → `browser_click_element` → `browser_extract_content`
2. **表单填写**: 使用`browser_input_text` → `browser_send_keys` → `browser_click_element`
3. **页面导航**: 使用`browser_navigate` → `browser_wait` → `browser_get_page_info`
4. **复杂任务**: 直接使用`browser_use_execute_task`进行AI自动化

## ⚠️ 重要提醒

- **参数格式**: 多个参数使用JSON格式: `{"param1": "value1", "param2": "value2"}`
- **元素索引**: 从页面的可访问性树中获取正确的元素索引
- **错误恢复**: 如果工具调用失败，检查参数格式和元素索引的有效性