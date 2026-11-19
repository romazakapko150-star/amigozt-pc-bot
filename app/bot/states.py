from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Configurator(StatesGroup):
    """Configurator FSM.

    The current question lives in the FSM *data* (``current_step``) rather than
    in a state per question: the flow graph in ``app.bot.flows.configurator``
    is the single source of truth for ordering. Only steps that accept free
    text need their own state, so that text messages can be routed correctly.
    """

    active = State()
    waiting_budget = State()
    waiting_game = State()
