from aiogram.fsm.state import State, StatesGroup


class ModuleCalculatorStates(StatesGroup):
    waiting_width = State()
    waiting_height = State()
    waiting_pixel_pitch = State()


class PowerCalculatorStates(StatesGroup):
    waiting_module_count = State()
    waiting_module_power = State()


class BomCalculatorStates(StatesGroup):
    waiting_screen_type = State()
    waiting_width = State()
    waiting_height = State()
    waiting_pixel_pitch = State()
    waiting_module_power = State()
    waiting_module_size = State()  # only for screen_type == open_frame
    waiting_psu_power = State()  # only when the type has no golden-standard PSU table
