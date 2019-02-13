from aiogram.dispatcher.filters.state import State, StatesGroup


# States
class Form(StatesGroup):
    initial = State()  # In storage as 'Form:initial'
    sender_name = State()  # In storage as 'Form:sender_name'
    sender_email = State()  # In storage as 'Form:sender_email'
    sender_address = State()  # In storage as 'Form:sender_address'
    sender_phone = State()  # In storage as 'Form:sender_phone'
    operational_mode = State()  # In storage as 'Form:operational_mode'
    violation_photo = State()  # In storage as 'Form:violation_photo'
    vehicle_number = State()  # In storage as 'Form:vehicle_number'
    violation_location = State()  # In storage as 'Form:violation_location'
    recipient = State()  # In storage as 'Form:recipient'
    violation_datetime = State()  # In storage as 'Form:violation_datetime'
    violation_sending = State()  # In storage as 'Form:violation_sending'
    feedback = State()  # In storage as 'Form:feedback'
    feedback_answering = State()  # In storage as 'Form:feedback_answering'
    caption = State()  # In storage as 'Form:caption'
