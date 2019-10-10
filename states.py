from aiogram.dispatcher.filters.state import State, StatesGroup


# States
class Form(StatesGroup):
    initial = State()  # In storage as 'Form:initial'
    sender_first_name = State()
    sender_last_name = State()
    sender_patronymic = State()
    sender_email = State()
    sender_city = State()
    sender_street = State()
    sender_house = State()
    sender_zipcode = State()
    operational_mode = State()
    violation_photo = State()
    vehicle_number = State()
    violation_location = State()
    recipient = State()
    violation_datetime = State()
    sending_approvement = State()
    feedback = State()
    feedback_answering = State()
    caption = State()
    email_verifying = State()
    letter_sending = State()
