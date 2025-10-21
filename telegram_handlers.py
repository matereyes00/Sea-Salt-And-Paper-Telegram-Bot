import os
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
# New imports for handling conversation history
from langchain_core.messages import HumanMessage, AIMessage
from utils.game_logic import calculate_score, calculate_color_bonus
from knowledge_base_manager import get_conversation_chain
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

def escape_markdown(text: str) -> str:
    """Escapes special characters for Telegram's MarkdownV2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Greets the user and tells them the bot is ready."""
    text = "Hello! I am the Game Master 🤖🎲\nAsk me anything about the rules of the current game or use the /score and /color_bonus commands!"
    escaped_text = escape_markdown(text)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=escaped_text,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles questions from the user using a history-aware chain."""
    # Lazy initialization of the RAG chain
    if "rag_chain" not in context.application.bot_data:
        vectorstore = context.application.bot_data["vectorstore"]
        context.application.bot_data["rag_chain"] = get_conversation_chain(vectorstore)
        logger.info("RAG chain initialized on first use.")
    
    rag_chain = context.application.bot_data["rag_chain"]
    user_question = update.message.text
    
    # Use context.chat_data to store history for each unique user
    if 'history' not in context.chat_data:
        context.chat_data['history'] = []

    thinking_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="🤔 Thinking..."
    )

    try:
        # Invoke the new chain with the user's input and their chat history
        response = await rag_chain.ainvoke({
            "input": user_question,
            "chat_history": context.chat_data.get('history', [])
        })

        local_answer = response.get("answer", "").strip()
        online_answer = None

        # --- Try fetching extra context online (parallel optional) ---
        try:
            online_answer = await fetch_online_info_with_gemini(user_question)
        except Exception as e:
            logger.warning(f"Gemini fallback failed: {e}")

        # --- Merge responses ---
        if local_answer and online_answer:
            answer = (
                f"🧩 **According to the rulebook:**\n{local_answer}\n\n"
                f"🌐 **From online sources:**\n{online_answer}"
            )
        elif local_answer:
            answer = local_answer
        elif online_answer:
            answer = f"🌐 *I couldn’t find this in the rulebook, but here’s what I found online:*\n\n{online_answer}"
        else:
            answer = "⚠️ Sorry, I couldn’t find any information on that — even online."

        # Update the user's chat history with the new exchange
        context.chat_data['history'].extend([
            HumanMessage(content=user_question),
            AIMessage(content=answer)
        ])
        
        # Keep the history from getting too long
        if len(context.chat_data['history']) > 8:
            context.chat_data['history'] = context.chat_data['history'][-8:]

        final_text = escape_markdown(str(answer))
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_message.message_id,
            text=final_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Error during conversation chain invocation: {e}")
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=thinking_message.message_id,
            text="⚠️ Sorry, I had trouble generating an answer. Please try asking again."
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logs errors."""
    logger.error(f"An error occurred: {context.error}")

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calculates the score for a list of cards."""
    user_input = update.message.text.partition(' ')[2]
    if not user_input:
        example_text = "Please list your cards after the command\\. \nExample: `/score 2 crabs, 4 shells`"
        await update.message.reply_text(text=example_text, parse_mode=ParseMode.MARKDOWN_V2)
        return
    response_text, _ = calculate_score(user_input)
    escaped_response = escape_markdown(response_text)
    await update.message.reply_text(text=escaped_response, parse_mode=ParseMode.MARKDOWN_V2)

async def color_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Ask user to choose the round outcome via inline buttons."""
    user_input = update.message.text.partition(' ')[2].strip()

    if not user_input:
        example_text = (
            "Please list your cards by color count. \n"
            "Example: `/color_bonus 4 blue, 3 pink, 1 mermaid`"
        )
        await update.message.reply_text(
            text=escape_markdown(example_text),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Save the card info temporarily (for callback use)
    context.user_data["color_bonus_input"] = user_input

    # Inline buttons for outcome selection
    keyboard = [
        [
            InlineKeyboardButton("Caller Win ✅ (You called + won)", callback_data="color_bonus_caller_win"),
            InlineKeyboardButton("Caller Fail ❌ (You called + lost)", callback_data="color_bonus_caller_fail"),
        ],
        [
            InlineKeyboardButton("Other Wins 🧍‍♂️ (Someone else called + won)", callback_data="color_bonus_other_win"),
            InlineKeyboardButton("Stop 🛑 (Normal end, no bonus)", callback_data="color_bonus_stop"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Choose how the round ended:",
        reply_markup=reply_markup
    )


async def handle_color_bonus_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Handle which color bonus scenario the user chose (with clarification text)."""
    query = update.callback_query
    await query.answer()  # Acknowledge button press

    user_input = context.user_data.get("color_bonus_input", "")
    if not user_input:
        await query.edit_message_text("⚠️ Please send `/color_bonus` again first.")
        return

    # Default flags
    called_last_chance, caller, caller_succeeded = True, True, True

    # --- Determine which option was chosen ---
    if query.data == "color_bonus_stop":
        called_last_chance = False
        clarification = "🛑 *Round ended normally with Stop* — no color bonus is scored."
    elif query.data == "color_bonus_caller_fail":
        caller_succeeded = False
        clarification = "❌ *You called Last Chance but lost* — you score only your color bonus."
    elif query.data == "color_bonus_other_win":
        caller = False
        caller_succeeded = True
        clarification = "🧍‍♂️ *Another player called Last Chance and succeeded* — you score only your color bonus."
    else:  # default: caller win
        clarification = "✅ *You called Last Chance and won* — you keep your full card points plus color bonus."

    # --- Compute color bonus using your logic ---
    bonus_points, explanation = calculate_color_bonus(
        user_input,
        called_last_chance=called_last_chance,
        caller=caller,
        caller_succeeded=caller_succeeded
    )

    # --- Combine clarification + result ---
    final_message = (
        f"{clarification}\n\n"
        f"🎨 *Color Bonus: {bonus_points} point(s)*\n\n"
        f"{explanation}"
    )

    escaped_response = escape_markdown(final_message)
    await query.edit_message_text(
        text=escaped_response,
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def fetch_online_info_with_gemini(query: str):
    """Fetches supporting online info using Gemini."""
    try:
        gemini = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            temperature=0.7,
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )

        prompt = (
            "Search for the most accurate and recent information about the card game "
            "'Sea Salt & Paper'. Summarize it concisely. If there’s overlap with rulebook info, clarify it.\n\n"
            f"Question: {query}"
        )

        response = await gemini.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    
    except Exception as e:
        logger.error(f"Gemini fetch failed: {e}")
        return None


def setup_telegram_bot(vectorstore, port: int, webhook_url: str):
    """Initializes and runs the Telegram bot with webhooks."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

    app = Application.builder().token(bot_token).build()
    app.bot_data["vectorstore"] = vectorstore

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler('score', score))
    app.add_handler(CommandHandler('color_bonus', color_bonus))
    app.add_handler(CallbackQueryHandler(handle_color_bonus_choice, pattern="^color_bonus_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info(f"Starting webhook server on 0.0.0.0:{port}")
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=bot_token,
        webhook_url=f"{webhook_url}/{bot_token}"
    )

def setup_telegram_bot_local(vectorstore):
    """Initializes and runs the Telegram bot in polling mode for local development."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

    app = Application.builder().token(bot_token).build()
    app.bot_data["vectorstore"] = vectorstore

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler('score', score))
    app.add_handler(CommandHandler('color_bonus', color_bonus))
    app.add_handler(CallbackQueryHandler(handle_color_bonus_choice, pattern="^color_bonus_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    
    logger.info("Bot is running in polling mode...")
    # This command fetches updates from Telegram directly.
    app.run_polling()
