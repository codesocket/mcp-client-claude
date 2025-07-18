import asyncio
import json
from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import logging

from simple_mcp_client import SimpleMCPClient, MCPResponse
from llm_inference import LLMInferenceService, ExecutionPlan, ToolCall


class ExecutionStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionStep:
    step_id: int
    tool_call: ToolCall
    status: ExecutionStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@dataclass
class IntelligentExecutionResult:
    query: str
    execution_plan: ExecutionPlan
    steps: List[ExecutionStep]
    synthesized_response: str
    success: bool
    total_execution_time: float


class IntelligentMCPClient:
    def __init__(self, mcp_client: SimpleMCPClient, llm_service: LLMInferenceService):
        self.mcp_client = mcp_client
        self.llm_service = llm_service
        self.logger = logging.getLogger(__name__)
        
    async def process_natural_language_query(self, 
                                           user_query: str, 
                                           delegated_user: Optional[str] = None,
                                           context: Dict[str, Any] = None) -> IntelligentExecutionResult:
        """
        Process a natural language query using LLM inference and MCP tool execution
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Step 1: Get available tools and resources
            tools_response = await self.mcp_client.list_tools()
            if tools_response.error:
                raise Exception(f"Failed to list tools: {tools_response.error}")
            
            available_tools = tools_response.result.get("tools", [])
            
            # Get resources (optional)
            available_resources = []
            try:
                resources_response = await self.mcp_client.list_resources()
                if not resources_response.error:
                    available_resources = resources_response.result.get("resources", [])
            except Exception as e:
                self.logger.warning(f"Could not fetch resources: {e}")
            
            # Step 2: Analyze query and create execution plan
            execution_plan = await self.llm_service.analyze_query_and_plan_tools(
                user_query=user_query,
                available_tools=available_tools,
                available_resources=available_resources,
                context=context
            )
            
            # Step 3: Execute the plan
            execution_steps = await self._execute_plan(execution_plan, delegated_user)
            
            # Step 4: Synthesize response
            tool_results = [step.result for step in execution_steps if step.result is not None]
            synthesized_response = await self.llm_service.synthesize_response(
                user_query=user_query,
                tool_results=tool_results,
                execution_plan=execution_plan
            )
            
            end_time = asyncio.get_event_loop().time()
            
            return IntelligentExecutionResult(
                query=user_query,
                execution_plan=execution_plan,
                steps=execution_steps,
                synthesized_response=synthesized_response,
                success=all(step.status == ExecutionStatus.COMPLETED for step in execution_steps),
                total_execution_time=end_time - start_time
            )
            
        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            
            return IntelligentExecutionResult(
                query=user_query,
                execution_plan=ExecutionPlan([], [], {}, ""),
                steps=[],
                synthesized_response=f"I encountered an error processing your query: {str(e)}",
                success=False,
                total_execution_time=end_time - start_time
            )
    
    async def process_natural_language_query_stream(self, 
                                                  user_query: str, 
                                                  delegated_user: Optional[str] = None,
                                                  context: Dict[str, Any] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a natural language query with streaming updates
        """
        yield {"type": "status", "message": "Analyzing your query..."}
        
        try:
            # Step 1: Get available tools
            yield {"type": "status", "message": "Fetching available tools..."}
            tools_response = await self.mcp_client.list_tools()
            if tools_response.error:
                yield {"type": "error", "message": f"Failed to list tools: {tools_response.error}"}
                return
            
            available_tools = tools_response.result.get("tools", [])
            
            # Step 2: Create execution plan
            yield {"type": "status", "message": "Creating execution plan..."}
            execution_plan = await self.llm_service.analyze_query_and_plan_tools(
                user_query=user_query,
                available_tools=available_tools,
                context=context
            )
            
            yield {
                "type": "plan", 
                "plan": {
                    "tools": [{"name": tc.name, "reasoning": tc.reasoning} for tc in execution_plan.tool_calls],
                    "execution_order": execution_plan.execution_order
                }
            }
            
            # Step 3: Execute tools with streaming
            tool_results = []
            for i, step_index in enumerate(execution_plan.execution_order):
                if step_index >= len(execution_plan.tool_calls):
                    continue
                    
                tool_call = execution_plan.tool_calls[step_index]
                
                yield {
                    "type": "tool_start", 
                    "tool": tool_call.name,
                    "step": i + 1,
                    "total": len(execution_plan.execution_order)
                }
                
                try:
                    # Check dependencies
                    dependencies = execution_plan.dependencies.get(str(step_index), [])
                    if not self._check_dependencies_completed(dependencies, tool_results):
                        yield {"type": "tool_skip", "tool": tool_call.name, "reason": "Dependencies not met"}
                        continue
                    
                    # Execute tool
                    result = await self.mcp_client.call_tool(
                        tool_call.name, 
                        tool_call.arguments, 
                        delegated_user
                    )
                    
                    if result.error:
                        yield {"type": "tool_error", "tool": tool_call.name, "error": result.error}
                        tool_results.append({"error": result.error})
                    else:
                        yield {"type": "tool_result", "tool": tool_call.name, "result": result.result}
                        tool_results.append(result.result)
                        
                except Exception as e:
                    yield {"type": "tool_error", "tool": tool_call.name, "error": str(e)}
                    tool_results.append({"error": str(e)})
            
            # Step 4: Synthesize response
            yield {"type": "status", "message": "Synthesizing response..."}
            synthesized_response = await self.llm_service.synthesize_response(
                user_query=user_query,
                tool_results=tool_results,
                execution_plan=execution_plan
            )
            
            yield {"type": "final_response", "response": synthesized_response}
            
        except Exception as e:
            yield {"type": "error", "message": f"Processing failed: {str(e)}"}
    
    async def _execute_plan(self, execution_plan: ExecutionPlan, delegated_user: Optional[str] = None) -> List[ExecutionStep]:
        """Execute the tool execution plan"""
        
        steps = []
        results_cache = {}
        
        for i, step_index in enumerate(execution_plan.execution_order):
            if step_index >= len(execution_plan.tool_calls):
                continue
                
            tool_call = execution_plan.tool_calls[step_index]
            step = ExecutionStep(
                step_id=step_index,
                tool_call=tool_call,
                status=ExecutionStatus.PENDING
            )
            
            try:
                # Check dependencies
                dependencies = execution_plan.dependencies.get(str(step_index), [])
                if not self._check_dependencies_completed(dependencies, results_cache):
                    step.status = ExecutionStatus.SKIPPED
                    step.error = "Dependencies not met"
                    steps.append(step)
                    continue
                
                # Execute tool
                step.status = ExecutionStatus.RUNNING
                step.start_time = asyncio.get_event_loop().time()
                
                # Enhance arguments with dependency results if needed
                enhanced_arguments = self._enhance_arguments_with_dependencies(
                    tool_call.arguments, 
                    dependencies, 
                    results_cache
                )
                
                result = await self.mcp_client.call_tool(
                    tool_call.name, 
                    enhanced_arguments, 
                    delegated_user
                )
                
                step.end_time = asyncio.get_event_loop().time()
                
                if result.error:
                    step.status = ExecutionStatus.FAILED
                    step.error = result.error
                else:
                    step.status = ExecutionStatus.COMPLETED
                    step.result = result.result
                    results_cache[step_index] = result.result
                    
            except Exception as e:
                step.status = ExecutionStatus.FAILED
                step.error = str(e)
                step.end_time = asyncio.get_event_loop().time()
            
            steps.append(step)
        
        return steps
    
    def _check_dependencies_completed(self, dependencies: List[int], results_cache: Dict[int, Any]) -> bool:
        """Check if all dependencies have been completed successfully"""
        return all(dep_id in results_cache for dep_id in dependencies)
    
    def _enhance_arguments_with_dependencies(self, 
                                           base_arguments: Dict[str, Any], 
                                           dependencies: List[int], 
                                           results_cache: Dict[int, Any]) -> Dict[str, Any]:
        """Enhance tool arguments with results from dependency tools"""
        
        enhanced_args = base_arguments.copy()
        
        # Simple enhancement: add dependency results as context
        if dependencies:
            dependency_results = [results_cache.get(dep_id) for dep_id in dependencies if dep_id in results_cache]
            if dependency_results:
                enhanced_args["_dependency_results"] = dependency_results
        
        return enhanced_args
    
    async def get_tool_suggestions(self, user_query: str) -> List[Dict[str, Any]]:
        """Get tool suggestions for a user query without executing"""
        
        try:
            tools_response = await self.mcp_client.list_tools()
            if tools_response.error:
                return []
            
            available_tools = tools_response.result.get("tools", [])
            
            execution_plan = await self.llm_service.analyze_query_and_plan_tools(
                user_query=user_query,
                available_tools=available_tools
            )
            
            suggestions = []
            for tool_call in execution_plan.tool_calls:
                # Find the tool definition
                tool_def = next((t for t in available_tools if t.get("name") == tool_call.name), None)
                suggestions.append({
                    "name": tool_call.name,
                    "description": tool_def.get("description", "") if tool_def else "",
                    "suggested_arguments": tool_call.arguments,
                    "reasoning": tool_call.reasoning,
                    "confidence": "high" if tool_def else "low"
                })
            
            return suggestions
            
        except Exception as e:
            self.logger.error(f"Failed to get tool suggestions: {e}")
            return []
    
    def clear_conversation_context(self):
        """Clear conversation context in LLM service"""
        self.llm_service.clear_conversation_history()