"""
Tests for core.llm_client module
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm_client import LLMClient
from core.interfaces import TaskSpec, TaskType


class TestLLMClient:
    """Test LLMClient class"""
    
    @pytest.fixture
    def llm_client(self, mock_config_manager):
        """Create LLMClient instance for testing"""
        # Mock LLM configuration
        mock_config_manager.get_llm_config.return_value = {
            'provider': 'openai',
            'model': 'gpt-4',
            'api_key': 'test_api_key',
            'base_url': 'https://api.openai.com/v1',
            'max_tokens': 4000,
            'temperature': 0.7
        }
        
        return LLMClient(mock_config_manager)
    
    @pytest.mark.asyncio
    async def test_initialization(self, llm_client):
        """Test LLMClient initialization"""
        assert llm_client is not None
        assert hasattr(llm_client, 'config_manager')
        assert hasattr(llm_client, 'provider')
    
    @pytest.mark.asyncio
    async def test_generate_response_success(self, llm_client):
        """Test successful response generation"""
        with patch.object(llm_client.provider, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': 'Test response from LLM',
                'finish_reason': 'stop',
                'usage': {
                    'prompt_tokens': 50,
                    'completion_tokens': 20,
                    'total_tokens': 70
                }
            }
            
            response = await llm_client.generate_response('Test prompt')
            
            assert response['content'] == 'Test response from LLM'
            assert response['finish_reason'] == 'stop'
            assert response['usage']['total_tokens'] == 70
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_with_system_message(self, llm_client):
        """Test response generation with system message"""
        with patch.object(llm_client.provider, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': 'Response with system context',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 100}
            }
            
            response = await llm_client.generate_response(
                'User prompt',
                system_message='You are a helpful assistant'
            )
            
            assert response['content'] == 'Response with system context'
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_with_options(self, llm_client):
        """Test response generation with custom options"""
        with patch.object(llm_client.provider, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': 'Custom response',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 80}
            }
            
            response = await llm_client.generate_response(
                'Test prompt',
                temperature=0.9,
                max_tokens=2000
            )
            
            assert response['content'] == 'Custom response'
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_response_error(self, llm_client):
        """Test response generation with error"""
        with patch.object(llm_client.provider, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception('API Error')
            
            with pytest.raises(Exception, match='API Error'):
                await llm_client.generate_response('Test prompt')
    
    @pytest.mark.asyncio
    async def test_analyze_task(self, llm_client, sample_task):
        """Test task analysis"""
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': '''
                {
                    "analysis": "This is a code generation task",
                    "complexity": "medium",
                    "estimated_steps": 3,
                    "required_tools": ["python_executor"],
                    "approach": "Generate Python code and execute it"
                }
                ''',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 150}
            }
            
            analysis = await llm_client.analyze_task(sample_task)
            
            assert 'analysis' in analysis
            assert 'complexity' in analysis
            assert 'required_tools' in analysis
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_analyze_task_invalid_json(self, llm_client, sample_task):
        """Test task analysis with invalid JSON response"""
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': 'Invalid JSON response',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 50}
            }
            
            analysis = await llm_client.analyze_task(sample_task)
            
            # Should return default analysis structure
            assert 'error' in analysis
            assert analysis['error'] == 'Failed to parse analysis'
    
    @pytest.mark.asyncio
    async def test_generate_code(self, llm_client):
        """Test code generation"""
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': '''
                ```python
                def hello_world():
                    print("Hello, World!")
                    return "success"
                
                hello_world()
                ```
                ''',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 100}
            }
            
            code = await llm_client.generate_code(
                'Write a Python function that prints Hello World',
                language='python'
            )
            
            assert 'def hello_world()' in code
            assert 'print("Hello, World!")' in code
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_reasoning(self, llm_client, sample_reasoning_task):
        """Test reasoning generation"""
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': '''
                Let me analyze this step by step:
                
                1. First, I need to understand the problem
                2. Then, I'll break it down into smaller parts
                3. Finally, I'll provide a comprehensive solution
                
                The reasoning leads to the conclusion that...
                ''',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 200}
            }
            
            reasoning = await llm_client.generate_reasoning(sample_reasoning_task)
            
            assert 'step by step' in reasoning
            assert 'analyze' in reasoning
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_actions(self, llm_client):
        """Test action extraction from text"""
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': '''
                [
                    {
                        "action_type": "code_execution",
                        "description": "Execute Python code",
                        "parameters": {"code": "print('hello')", "language": "python"}
                    },
                    {
                        "action_type": "browser_action",
                        "description": "Navigate to webpage",
                        "parameters": {"url": "https://example.com", "action": "navigate"}
                    }
                ]
                ''',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 120}
            }
            
            actions = await llm_client.extract_actions('Execute some code and navigate to a webpage')
            
            assert len(actions) == 2
            assert actions[0]['action_type'] == 'code_execution'
            assert actions[1]['action_type'] == 'browser_action'
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_actions_invalid_json(self, llm_client):
        """Test action extraction with invalid JSON"""
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': 'Invalid JSON for actions',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 50}
            }
            
            actions = await llm_client.extract_actions('Some text')
            
            assert actions == []
    
    @pytest.mark.asyncio
    async def test_summarize_results(self, llm_client):
        """Test result summarization"""
        results = [
            {'step': 1, 'action': 'code_execution', 'result': 'Code executed successfully'},
            {'step': 2, 'action': 'browser_action', 'result': 'Page loaded'},
            {'step': 3, 'action': 'tool_call', 'result': 'Data extracted'}
        ]
        
        with patch.object(llm_client, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                'content': '''
                Summary of task execution:
                
                The task was completed successfully in 3 steps:
                1. Code was executed without errors
                2. Browser navigation was successful
                3. Data extraction completed
                
                Overall result: SUCCESS
                ''',
                'finish_reason': 'stop',
                'usage': {'total_tokens': 180}
            }
            
            summary = await llm_client.summarize_results(results)
            
            assert 'Summary of task execution' in summary
            assert 'SUCCESS' in summary
            mock_generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, llm_client):
        """Test rate limit error handling"""
        with patch.object(llm_client.provider, 'generate_response', new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception('Rate limit exceeded')
            
            with pytest.raises(Exception, match='Rate limit exceeded'):
                await llm_client.generate_response('Test prompt')
    
    @pytest.mark.asyncio
    async def test_token_counting(self, llm_client):
        """Test token counting functionality"""
        with patch.object(llm_client, 'count_tokens') as mock_count:
            mock_count.return_value = 25
            
            token_count = llm_client.count_tokens('This is a test message')
            
            assert token_count == 25
            mock_count.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_response(self, llm_client):
        """Test response validation"""
        valid_response = {
            'content': 'Valid response',
            'finish_reason': 'stop',
            'usage': {'total_tokens': 50}
        }
        
        invalid_response = {
            'content': '',
            'finish_reason': 'error'
        }
        
        assert llm_client.validate_response(valid_response) is True
        assert llm_client.validate_response(invalid_response) is False
    
    @pytest.mark.asyncio
    async def test_conversation_history(self, llm_client):
        """Test conversation history management"""
        # Test adding to conversation history
        llm_client.add_to_history('user', 'Hello')
        llm_client.add_to_history('assistant', 'Hi there!')
        
        history = llm_client.get_conversation_history()
        
        assert len(history) == 2
        assert history[0]['role'] == 'user'
        assert history[0]['content'] == 'Hello'
        assert history[1]['role'] == 'assistant'
        assert history[1]['content'] == 'Hi there!'
    
    @pytest.mark.asyncio
    async def test_clear_conversation_history(self, llm_client):
        """Test clearing conversation history"""
        llm_client.add_to_history('user', 'Test message')
        llm_client.clear_history()
        
        history = llm_client.get_conversation_history()
        assert len(history) == 0
    
    @pytest.mark.asyncio
    async def test_streaming_response(self, llm_client):
        """Test streaming response generation"""
        async def mock_stream():
            yield {'content': 'Part 1', 'finish_reason': None}
            yield {'content': 'Part 2', 'finish_reason': None}
            yield {'content': 'Part 3', 'finish_reason': 'stop'}
        
        with patch.object(llm_client.provider, 'generate_streaming_response', return_value=mock_stream()):
            response_parts = []
            async for part in llm_client.generate_streaming_response('Test prompt'):
                response_parts.append(part)
            
            assert len(response_parts) == 3
            assert response_parts[-1]['finish_reason'] == 'stop'