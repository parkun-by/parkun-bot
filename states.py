from aiogram.dispatcher.filters.state import State, StatesGroup


# States
class Form(StatesGroup):
    initial = State()  # In storage as 'Form:initial'
    sender_name = State()  # In storage as 'Form:sender_name'
    sender_email = State()  # In storage as 'Form:sender_email'
    sender_adress = State()  # In storage as 'Form:sender_adress'
    sender_phone = State()  # In storage as 'Form:sender_phone'
    operational_mode = State()  # In storage as 'Form:operational_mode'
    vehicle_number = State()  # In storage as 'Form:vehicle_number'
    violation_location = State()  # In storage as 'Form:violation_location'
    violation_datetime = State()  # In storage as 'Form:violation_datetime'
    violation_sending = State()  # In storage as 'Form:violation_sending'
    feedback = State()  # In storage as 'Form:feedback'
