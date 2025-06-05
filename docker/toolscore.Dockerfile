# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

ENV PYTHONPATH=/app

# Install build tools required for some Python packages (e.g., pandas)

# Install any needed packages specified in requirements.txt
# Assuming core/toolscore might have its own requirements or share global ones
# For now, we'll assume core/toolscore's dependencies are covered by the main requirements.txt
# If core/toolscore has specific dependencies, they should be listed in a separate requirements file
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the entire core/toolscore directory into the container
COPY core/toolscore /app/core/toolscore
COPY core/interfaces.py /app/core/interfaces.py
COPY core/utils.py /app/core/utils.py
COPY core/cache.py /app/core/cache.py
COPY core/llm_client.py /app/core/llm_client.py
COPY core/metrics.py /app/core/metrics.py
COPY core/browser_state_manager.py /app/core/browser_state_manager.py
COPY core/dispatcher.py /app/core/dispatcher.py
COPY core/dispatcher_enhanced.py /app/core/dispatcher_enhanced.py
COPY core/router.py /app/core/router.py
COPY core/task_manager.py /app/core/task_manager.py
COPY core/tool_registry.py /app/core/tool_registry.py
COPY core/__init__.py /app/core/__init__.py

# Expose the port the MCP server will run on
EXPOSE 8080

# Run the MCP server when the container launches
CMD ["python", "-m", "core.toolscore.mcp_server"]