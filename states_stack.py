from logging import Logger
from typing import Any, Awaitable, Callable, Tuple, Optional, Union
from aiogram.dispatcher import FSMContext, Dispatcher
from aiogram.types import Message
from states import Form


class StatesStack:
    def __init__(self,
                 logger: Logger,
                 dp: Dispatcher,
                 get_value: Callable,
                 get_lang: Callable,
                 get_text: Callable):
        self.logger = logger
        self.dispatcher = dp
        self.get_value = get_value
        self.get_ui_lang = get_lang
        self.get_text = get_text

    async def add(self,
                  user_id: int,
                  data_to_save={},
                  recover_message='') -> None:
        state = self.dispatcher.current_state(chat=user_id, user=user_id)

        async with state.proxy() as data:
            stack: list = self.get_value(data, 'states_stack')
            current_state = await state.get_state()

            state_to_save = {
                'state': current_state,
                'data': data_to_save,
                'message_id': self.get_value(data, 'message_to_answer'),
                'message_text': recover_message
            }

            stack.append(state_to_save)
            data['states_stack'] = stack

    async def pop(self, user_id: int) -> Tuple[int, str]:
        state = self.dispatcher.current_state(chat=user_id, user=user_id)

        async with state.proxy() as data:
            language = await self.get_ui_lang(data=data)
            stack: list = self.get_value(data, 'states_stack')

            if stack:
                state_to_apply = stack.pop()
            else:
                state_to_apply = {
                    'state': Form.operational_mode.state,
                    'data': {},
                    'message_id': 0,
                    'message_text': self.get_text(language, 'operation_mode'),
                }

            state_to_set = state_to_apply['state']
            data_to_set = state_to_apply['data']
            message_id = state_to_apply['message_id']
            message_text: str = state_to_apply['message_text']

            if not message_id and not message_text:
                message_text = self.get_text(language, 'continue_work')

            if state_to_set == Form.operational_mode.state:
                message_text = self.get_text(language, 'operation_mode')

            await state.set_state(state_to_set)
            self.set_data(data_to_set, data)
            data['message_to_answer'] = message_id
            data['states_stack'] = stack

        return message_id, message_text

    def set_data(self, data_to_set: dict, data: dict) -> None:
        for key in data_to_set:
            data[key] = data_to_set[key]
