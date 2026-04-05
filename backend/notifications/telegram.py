import logging
import httpx
from typing import Optional
from config.settings import settings

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Sends notifications to Telegram via Bot API."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    @property
    def is_enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send_message(self, text: str):
        if not self.is_enabled:
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self.base_url,
                    json={
                        "chat_id": self.chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    }
                )
                resp.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    async def notify_execution(self, execution: dict):
        """Notify about a specific trade execution."""
        if not self.is_enabled:
            return

        ticker = execution.get("ticker", "UNKNOWN")
        action = execution.get("action", "hold").upper()
        status = execution.get("status", "unknown").upper()
        price = execution.get("filled_price")
        qty = execution.get("quantity", 0)
        confidence = execution.get("confidence", 0) * 100
        reasons = "\n".join([f"• {r}" for r in execution.get("reasons", [])[:3]])

        if status == "SKIPPED":
            return

        icon = "🟢" if action == "BUY" else "🔴"
        if status == "FILLED":
            msg = (
                f"{icon} <b>TRADE {action} FILLED</b>\n\n"
                f"<b>Ticker:</b> {ticker}\n"
                f"<b>Price:</b> ${price:.2f}\n"
                f"<b>Quantity:</b> {qty}\n"
                f"<b>Confidence:</b> {confidence:.0f}%\n\n"
                f"<b>Reasons:</b>\n{reasons}"
            )
        else:
            msg = f"⚠️ <b>TRADE {action} FAILED</b>\n<b>Ticker:</b> {ticker}\n<b>Status:</b> {status}"

        await self.send_message(msg)

    async def notify_cycle_summary(self, result: dict):
        """Notify about an auto-trade cycle completion."""
        if not self.is_enabled:
            return

        p = result.get("portfolio", {})
        val = p.get("total_value", 0)
        pnl = p.get("total_pnl", 0)
        pnl_pct = p.get("total_pnl_pct", 0)
        pos_count = p.get("positions_count", 0)

        icon = "📈" if pnl >= 0 else "📉"
        
        msg = (
            f"📊 <b>CYCLE COMPLETE</b>\n\n"
            f"<b>Total Value:</b> ${val:,.2f}\n"
            f"<b>PnL:</b> {icon} ${pnl:,.2f} ({pnl_pct:+.2f}%)\n"
            f"<b>Positions:</b> {pos_count}\n"
        )
        
        executions = result.get("executions", [])
        filled = [e for e in executions if e.get("status") == "filled"]
        if filled:
            msg += f"\n✅ <b>Executed {len(filled)} trades.</b>"
        
        await self.send_message(msg)
