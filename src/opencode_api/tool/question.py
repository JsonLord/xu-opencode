"""Question tool - allows agent to ask user questions during execution."""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import asyncio
import logging

from .tool import BaseTool, ToolResult, ToolContext
from ..core.identifier import generate_id
from ..core.bus import Bus

logger = logging.getLogger(__name__)


# Question schemas
class QuestionOption(BaseModel):
    """A single option for a question."""
    label: str = Field(..., description="Display text (1-5 words, concise)")
    description: str = Field(..., description="Explanation of choice")


class QuestionInfo(BaseModel):
    """A question to ask the user."""
    question: str = Field(..., description="Complete question")
    header: str = Field(..., description="Very short label (max 30 chars)")
    options: List[QuestionOption] = Field(default_factory=list, description="Available choices")
    multiple: bool = Field(default=False, description="Allow selecting multiple choices")
    custom: bool = Field(default=True, description="Allow typing a custom answer")


class QuestionRequest(BaseModel):
    """A request containing questions for the user."""
    id: str
    session_id: str
    questions: List[QuestionInfo]
    tool_call_id: Optional[str] = None
    message_id: Optional[str] = None


class QuestionReply(BaseModel):
    """User's reply to questions."""
    request_id: str
    answers: List[List[str]] = Field(..., description="Answers in order (each is array of selected labels)")


# Events
QUESTION_ASKED = "question.asked"
QUESTION_REPLIED = "question.replied"
QUESTION_REJECTED = "question.rejected"


# Pending questions state
_pending_questions: Dict[str, asyncio.Future] = {}


async def ask_questions(
    session_id: str,
    questions: List[QuestionInfo],
    tool_call_id: Optional[str] = None,
    message_id: Optional[str] = None,
    timeout: float = 300.0,  # 5 minutes default timeout
) -> List[List[str]]:
    """Ask questions and wait for user response."""
    # tool_call_id를 request_id로 사용 (프론트엔드에서 바로 사용 가능)
    request_id = tool_call_id or generate_id("question")
    
    request = QuestionRequest(
        id=request_id,
        session_id=session_id,
        questions=questions,
        tool_call_id=tool_call_id,
        message_id=message_id,
    )
    
    # Create future for response
    # 중요: get_running_loop() 사용 (get_event_loop()는 FastAPI에서 잘못된 loop 반환 가능)
    loop = asyncio.get_running_loop()
    future: asyncio.Future[List[List[str]]] = loop.create_future()
    _pending_questions[request_id] = future
    
    # Publish question event (will be sent via SSE)
    await Bus.publish(QUESTION_ASKED, request.model_dump())
    
    try:
        # Wait for reply with timeout
        logger.info(f"[question] Waiting for answer to request_id={request_id}, timeout={timeout}s")
        answers = await asyncio.wait_for(future, timeout=timeout)
        logger.info(f"[question] Received answer for request_id={request_id}: {answers}")
        return answers
    except asyncio.TimeoutError:
        logger.error(f"[question] Timeout for request_id={request_id} after {timeout}s")
        del _pending_questions[request_id]
        raise TimeoutError(f"Question timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"[question] Error waiting for answer: {type(e).__name__}: {e}")
        raise
    finally:
        if request_id in _pending_questions:
            del _pending_questions[request_id]


async def reply_to_question(request_id: str, answers: List[List[str]]) -> bool:
    """Submit answers to a pending question."""
    logger.info(f"[question] reply_to_question called: request_id={request_id}, answers={answers}")
    logger.info(f"[question] pending_questions keys: {list(_pending_questions.keys())}")

    if request_id not in _pending_questions:
        logger.error(f"[question] request_id={request_id} NOT FOUND in pending_questions!")
        return False

    future = _pending_questions[request_id]
    if not future.done():
        logger.info(f"[question] Setting result for request_id={request_id}")
        future.set_result(answers)
    else:
        logger.warning(f"[question] Future already done for request_id={request_id}")

    return True


async def reject_question(request_id: str) -> bool:
    """Reject/dismiss a pending question."""
    if request_id not in _pending_questions:
        return False
    
    future = _pending_questions[request_id]
    if not future.done():
        future.set_exception(QuestionRejectedError())
    
    return True


def get_pending_questions(session_id: Optional[str] = None) -> List[str]:
    """Get list of pending question request IDs."""
    return list(_pending_questions.keys())


class QuestionRejectedError(Exception):
    """Raised when user dismisses a question."""
    def __init__(self):
        super().__init__("The user dismissed this question")


QUESTION_DESCRIPTION = """Use this tool when you need to ask the user questions during execution. This allows you to:
1. Gather user preferences or requirements
2. Clarify ambiguous instructions
3. Get decisions on implementation choices as you work
4. Offer choices to the user about what direction to take.

IMPORTANT: You MUST provide at least 2 options for each question. Never ask open-ended questions without choices.

Usage notes:
- REQUIRED: Every question MUST have at least 2 options (minItems: 2)
- When `custom` is enabled (default), a "Type your own answer" option is added automatically; don't include "Other" or catch-all options
- Answers are returned as arrays of labels; set `multiple: true` to allow selecting more than one
- If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label
"""


class QuestionTool(BaseTool):
    """Tool for asking user questions during execution."""
    
    @property
    def id(self) -> str:
        return "question"
    
    @property
    def description(self) -> str:
        return QUESTION_DESCRIPTION
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "Questions to ask",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Complete question"
                            },
                            "header": {
                                "type": "string",
                                "description": "Very short label (max 30 chars)"
                            },
                            "options": {
                                "type": "array",
                                "description": "Available choices (MUST provide at least 2 options)",
                                "minItems": 2,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {
                                            "type": "string",
                                            "description": "Display text (1-5 words, concise)"
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": "Explanation of choice"
                                        }
                                    },
                                    "required": ["label", "description"]
                                }
                            },
                            "multiple": {
                                "type": "boolean",
                                "description": "Allow selecting multiple choices",
                                "default": False
                            }
                        },
                        "required": ["question", "header", "options"]
                    }
                }
            },
            "required": ["questions"]
        }
    
    async def execute(self, args: Dict[str, Any], ctx: ToolContext) -> ToolResult:
        logger.info(f"[question] execute called with args: {args}")
        logger.info(f"[question] args type: {type(args)}")

        questions_data = args.get("questions", [])
        logger.info(f"[question] questions_data type: {type(questions_data)}, len: {len(questions_data) if isinstance(questions_data, list) else 'N/A'}")

        if questions_data and len(questions_data) > 0:
            logger.info(f"[question] first question type: {type(questions_data[0])}")
            logger.info(f"[question] first question content: {questions_data[0]}")
        
        if not questions_data:
            return ToolResult(
                title="No questions",
                output="No questions were provided.",
                metadata={}
            )
        
        # Parse questions
        questions = []
        try:
            for idx, q in enumerate(questions_data):
                logger.info(f"[question] Parsing question {idx}: type={type(q)}, value={q}")

                # q가 문자열인 경우 처리
                if isinstance(q, str):
                    logger.error(f"[question] Question {idx} is a string, not a dict!")
                    continue

                options = []
                for opt_idx, opt in enumerate(q.get("options", [])):
                    logger.info(f"[question] Parsing option {opt_idx}: type={type(opt)}, value={opt}")
                    if isinstance(opt, dict):
                        options.append(QuestionOption(label=opt["label"], description=opt["description"]))
                    else:
                        logger.error(f"[question] Option {opt_idx} is not a dict: {type(opt)}")

                questions.append(QuestionInfo(
                    question=q["question"],
                    header=q["header"],
                    options=options,
                    multiple=q.get("multiple", False),
                    custom=q.get("custom", True),
                ))
        except Exception as e:
            logger.error(f"[question] Error parsing questions: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[question] Traceback: {traceback.format_exc()}")
            raise
        
        try:
            # Ask questions and wait for response
            answers = await ask_questions(
                session_id=ctx.session_id,
                questions=questions,
                tool_call_id=ctx.tool_call_id,
                message_id=ctx.message_id,
            )
            
            # Format response
            def format_answer(answer: List[str]) -> str:
                if not answer:
                    return "Unanswered"
                return ", ".join(answer)
            
            formatted = ", ".join(
                f'"{q.question}"="{format_answer(answers[i] if i < len(answers) else [])}"'
                for i, q in enumerate(questions)
            )
            
            return ToolResult(
                title=f"Asked {len(questions)} question{'s' if len(questions) > 1 else ''}",
                output=f"User has answered your questions: {formatted}. You can now continue with the user's answers in mind.",
                metadata={"answers": answers}
            )
            
        except QuestionRejectedError:
            return ToolResult(
                title="Questions dismissed",
                output="The user dismissed the questions without answering.",
                metadata={"rejected": True}
            )
        except TimeoutError as e:
            return ToolResult(
                title="Questions timed out",
                output=str(e),
                metadata={"timeout": True}
            )
