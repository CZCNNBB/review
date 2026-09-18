from langchain_core.messages import AIMessageChunk, ToolMessage

# ------------------------- 消息处理函数 -----------------------

# AIMessageChunk是langchain中表示AI生成的消息块的类，通常用于流式响应中
# ToolMessage是langchain中表示工具调用结果的类

def _process_ai_message(msg: AIMessageChunk) -> dict:
    """处理AI消息块"""
    # 如果消息包含工具调用块，则返回工具调用信息
    if msg.tool_call_chunks:
        return {
            "type": "tool_call",
            "tool_info": [
                {
                    "name": tc.get("name"), 
                    "args": tc.get("args")
                    } 
                for tc in msg.tool_call_chunks
            ]
        }
    else:
        return {
            "type": "answer",
            "content": msg.content
            }


def _process_tool_message(msg: ToolMessage) -> dict:
    """处理工具消息"""
    return {
        "type": "tool_result",
        "content": msg.content,
        "tool_info": {
            "tool_name": msg.name, 
            "tool_call_id": msg.tool_call_id
        }
    }