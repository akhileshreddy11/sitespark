from sqlalchemy.orm import Session
from app.models import Lead, LeadState, StateEvent, now

ALLOWED = {
    LeadState.found: {LeadState.enriched, LeadState.rejected, LeadState.error},
    LeadState.enriched: {LeadState.demo_generating, LeadState.rejected, LeadState.error},
    LeadState.demo_generating: {LeadState.demo_ready, LeadState.demo_failed, LeadState.error},
    LeadState.demo_failed: {LeadState.demo_generating, LeadState.error},
    LeadState.demo_ready: {LeadState.contacted, LeadState.error},
    LeadState.contacted: {LeadState.replied, LeadState.paid, LeadState.unsubscribed, LeadState.error},
    LeadState.replied: {LeadState.paid, LeadState.unsubscribed, LeadState.error},
    LeadState.paid: {LeadState.live, LeadState.error},
    LeadState.live: {LeadState.churned, LeadState.error},
    LeadState.error: {LeadState.found, LeadState.enriched, LeadState.rejected},
    LeadState.rejected: set(), LeadState.churned: set(), LeadState.unsubscribed: set(),
}


def transition(db: Session, lead: Lead, target: LeadState, reason: str | None = None) -> None:
    if target not in ALLOWED[lead.state]:
        raise ValueError(f"Invalid transition: {lead.state.value} -> {target.value}")
    previous = lead.state
    lead.state = target
    lead.state_changed_at = now()
    db.add(StateEvent(lead_id=lead.id, from_state=previous.value, to_state=target.value, reason=reason))
