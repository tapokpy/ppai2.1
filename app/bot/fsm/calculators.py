from aiogram.fsm.state import State, StatesGroup


class ModuleCalculatorStates(StatesGroup):
    waiting_width = State()
    waiting_height = State()
    waiting_pixel_pitch = State()


class PowerCalculatorStates(StatesGroup):
    waiting_module_count = State()
    waiting_module_power = State()
