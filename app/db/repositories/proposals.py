from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.proposal import ProposalDecisionModel, ProposalModel


def list_pending_proposals(db: Session) -> list[ProposalModel]:
    statement = select(ProposalModel).where(ProposalModel.confirmation_state == "pending")
    return list(db.scalars(statement))


def get_proposal(db: Session, proposal_id: str) -> ProposalModel | None:
    return db.get(ProposalModel, proposal_id)


def create_proposal(db: Session, proposal: ProposalModel) -> ProposalModel:
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def save_proposal(db: Session, proposal: ProposalModel) -> ProposalModel:
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def list_proposal_decisions(db: Session, proposal_id: str) -> list[ProposalDecisionModel]:
    statement = select(ProposalDecisionModel).where(ProposalDecisionModel.proposal_id == proposal_id)
    return list(db.scalars(statement))


def get_proposal_decision(db: Session, decision_id: str) -> ProposalDecisionModel | None:
    return db.get(ProposalDecisionModel, decision_id)


def create_proposal_decision(db: Session, decision: ProposalDecisionModel) -> ProposalDecisionModel:
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision
