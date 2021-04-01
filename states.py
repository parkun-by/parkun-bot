from aiogram.dispatcher.filters.state import State, StatesGroup


# States
class Form(StatesGroup):
    initial = State()  # In storage as 'Form:initial'
    sender_first_name = State()
    sender_last_name = State()
    sender_patronymic = State()
    sender_email = State()
    sender_phone = State()
    sender_city = State()
    sender_street = State()
    sender_house = State()
    sender_block = State()
    sender_flat = State()
    sender_zipcode = State()
    operational_mode = State()
    violation_photo = State()
    vehicle_number = State()
    violation_address = State()
    recipient = State()
    violation_datetime = State()
    sending_approvement = State()
    feedback = State()
    user_id_input = State()
    message_to_user = State()
    caption = State()
    email_verifying = State()
    entering_captcha = State()
    email_password = State()
    no_city_in_address = State()
    police_response = State()
    broadcasting = State()
