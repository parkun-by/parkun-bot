# Бот для облегчения посылки обращений о нарушении правил парковки в ГАИ (<https://faq.rfrm.io/parking.html>)

Бот умеет прикреплять присланные фотографии к [обращению](https://mvd.gov.by/ru/electronicAppealLogin) и заполнять его вашими личными данными и информацией о нарушении. После отправлять его. Также фото нарушений отправляются в [телеграм-канал](http://t.me/parkun) и [твиттер](https://twitter.com/parkun_bot).

Работает по всей Беларуси.

Бот развернут по адресу <http://t.me/parkun_by_bot>.

Одобряются issue, pull requests и прочие привнесения. [Инструкция для разработчиков.](./docs/russian/developers_guide.md)

Спасибо за внимание.

***

## Changelog

### 3.1.4

- Починил, сломанный в предыдущей версии, телеграф.

### 3.1.3

- На шаге ввода адреса, команды выбора предыдущего адреса заменены на кнопки под сообщением. Кажется, так будет более удобно.

### 3.1.2

- Дополнительное логгирование.

### 3.1.1

- Появилась странная ошибка, банов нет, но бот определяет, что пользователь забанен и потом падает потому что там, где должна быть причина бана, причины, очевидно, нет. Добавил там логгирования и обернул в try. Будем наблюдать.
- Минорно обновлен python.

### 3.1.0

- Добавлена возможность посылать сообщение конкретному пользователю бота.

### 3.0.7

- Более подробное логгирование, в лог включается никнейм.

### 3.0.6

- Cообщения rabbitmq пишутся на диск и переживают рестарт.

### 3.0.5

- Еще более лучшее определение того, что пользователь вводит номер, который уже выбран кнопочками.

### 3.0.4

- Не добавлять введенный гос. номер, если он уже был выбран кнопками (почему-то так бывает).

### 3.0.3

- Более красивый UI-переход если бот не смог распознать номера.

### 3.0.2

- Поправлен баг при отправке если не распознался ни один номер на фото.

### 3.0.1

- Поправлен баг. Если не выбрано ни одного распознанного номера, то не появлялось сообщение об этом при нажатии на кнопку завершения выбора.

### 3.0.0

- Добавлено распознавание гос. номеров ТС на присланных пользователями фотографиях.
- Изменен порядок ввода данных на "адрес -> время -> гос. номер"

### 2.18.2

- Оптимизация, исправление ошибок
- Добавлено сообщение о задержке при отправке обращений из-за неработы сайта МВД.

### 2.18.1

- Если при отправке бот не может достучаться до ящика, который указал пользователь, то он отсылает обращение со своего ящика. Пользователю присылается об этом сообщение.
- Жыве Беларусь.

### 2.18.0

- Повышена надежность отправки постов в социальные сети после отправки обращения.
- Уменьшены негативные последствия рестарта бота для пользователей, которые были в процессе отправки нарушения.
- В постах #ответГАИ в канале теперь ссылка на нарушение подписана как "Нарушение:".
- В имя файла с обращением, который присылается после отправки, теперь включен номер обращения.
- В настройках добавлена кнопка для очистки списка сохраненных адресов нарушения.

### 2.17.3

- При нажатии кнопок, не актуальных в текущем режиме бота, бот будет подсказывать чего от в данный момент ожидает от пользователя.

### 2.17.2

- Добавлено автоматическое возвращение в режим ввода нарушения из режима ввода фидбека через час после простоя.

### 2.17.1

- Немного повышена надежность старта бота.
- [Отправитель] Исправлена ошибка, когда в обращении из очереди нет email пользователя, но есть пароль и этот пароль применяется к стандартному email бота. В результате бот не может попасть в ящик.

### 2.17.0

- Загрузка границ регионов теперь происходит асинхронно с запуском бота.
- Планировщик теперь умеет планировать практически любые задания.
- Хранилище бота переписано на прямой доступ к redis вместо хождения через хранилище aiogram.
- Если на старте загрузка границы региона не удалась, то будет поставлено задание загрузить ее позже.
- При отправке теперь проверяется есть ли доступ к ящику пользователя, если пользователь указал пароль. Если доступа нет, то обращение отправляется с ящика бота.

### 2.16.3

- Добавлена случайная пауза при загрузке следующей границы региона при старте бота.

### 2.16.2

- При вводе адреса, где кроме команды адреса есть еще какой-то левый текст, бот будет ругаться и предлагать ввести адрес еще раз.
- Исправление мелких ошибок.
- Улучшение логгирования.

### 2.16.1

- Мелкое изменение способа запуска задач планировщика.

### 2.16.0

- При вводе ответа ГАИ теперь бот вернется в режим ожидания нарушения в случае, если ответ ГАИ не будет прислан в течение часа.
- Для разработчиков добавлена возможность создавать задания, срабатывающие в определенное время для определенного пользоваетеля.

### 2.15.2

- Актуализирована документация.

### 2.15.1

- Исправлена ошибка когда не присылался пример обращения из-за того, что не заполнены личные данные.

### 2.15.0

- [Broadcaster] добавлена пересылка постов с нарушениями в VK.

### 2.14.2

- Дополнительная статистика про общее количество людей, когда-либо входивших в бота.
- Команда /help немного перекомпонована. Пример обращения теперь генерируется из личных данных пользователя.
- Баны теперь распространяются и на отправку ответов ГАИ. Банить можно только по Telegram Id.

### 2.14.1

- Мелкое улучшение логгирования.

### 2.14.0

- Добавлена подсказка при вводе телефона, почему его стоит ввести.
- Посылка фидбека улучшена, можно отправлять любые сообщения и отвечать на сообщения поддержки.
- Администратору добавлена возможность писать сообщения пользователям от имени бота.
- Добавлена возможность посылать произвольный пост (одно фото + текст или просто текст) в социальные сети.
- Добавлена возможность администратору посылать любое сообщение всем пользователям разом.

### 2.13.5

- Исправлена ошибка при отправке поста с нарушением по соцсетям.

### 2.13.4

- Текстовые ответы ГАИ научились расшариваться в твиттер.
- Изменения в тексте адресов, ссылающихся на репозиторий бота в связи с переездом репозитория бота и всего остального [на новый адрес](https://github.com/parkun-by).

### 2.13.3

- Природа настолько очистилась, что в текст обращения вернулся "https:/".
- В текст обращения теперь вставляется дата отправки обращения и уникальный номер обращения.
- Ответы из ГАИ теперь шарятся во все соцсети, в которых представлен бот.

### 2.13.2

- Если кнопка отправки ответа ГАИ нажата ранее, чем через два дня после отправки обращения, то бот отвечает, что ответы не приходят так быстро и не предлагает отправить ответ в канал.

### 2.13.1

- Отправка нарушения в соцсети выделена в отдельный сервис. Пока что там только твиттер, но будет проще реализовать еще что-нибудь.

### 2.13.0

- Добавлена возможность присылать в [канал](t.me/parkun) ответы ГАИ с помощью бота. Для этого нужно переслать пост из канала, на который пришел ответ или нажать на кнопу, которую предоставляет бот после отправки обращения.

### 2.12.1

- В статистику по команде ``/stats`` было добавлено количество отправленных за сегодня и за вчера.
- Исправление ошибок отображения статистики.

### 2.12.0

- Добавлена возможность получить статистику по команде ``/stats``
- Мелкие улучшения.

### 2.11.2

- Пометка про адрес под стеклом при отправке фото.
- Исправление мелких ошибок.

### 2.11.1

- Фотографии стали еще более лучше отправляться, задержки после нажатия на кнопку отправить обращение практически нет.

### 2.11.0

- В текст обращения теперь добавляется ссылка на страницу со всеми фотографиями нарушения.
- Небольшая замена в тексте обращения "стоянки" на "остановки и стоянки".
- Работы по уменьшению времени отклика кнопки отправки обращения.

### 2.10.3

- Кнопка города и кнопка, что все окей с адресом поменяны местами.

### 2.10.2

- Немного более строгая проверка на наличие города в адресе нарушения.

### 2.10.1

- Ускорена реакция на нажатие кнопки отправки обращения.
- Убран один шаг из процесса когда пользователю предлагается дописать населенный пункт к адресу нарушения.

### 2.10.0

- Примитивный контроль за присутствием в адресе нарушения города.
- На вводе адреса добавлена инфа о том, что дополнительную информацию можно будет ввести позже.
- Мелкие улучшения.

### 2.9.2

- Подготовка бота к деплою с помощью docker hub.

### 2.9.1

- Текст обращения дополнен указанием на то, что обращение считается информацией о проишествии.
- [Отправитель] Повышение надежности.
- Уменьшение мусорного вывода в логи бота.

### 2.9.0

- Добавлена возможность отправки обращения в конкретный район Минска. Район определяется автоматически. Как и раньше можно перевыбрать вручную.

### 2.8.1

- Исправлено отображение адреса отправителя. Теперь нет больше лишних запятых.

### 2.8.0

- Переделано меню ввода данных об отправителе нарушения. Появилась навигация по данным и возможность досрочно завершить ввод.

### 2.7.1

- Обновлен python до 3.8.2.
- Починена ошибка, когда в саммари обращения подставлялась не та дата, которая была введена.

### 2.7.0

- При введении всех данных, которые требуются для отправки обращения, пользователю теперь предлагается отправить неотправленное из-за этого обращение, если оно есть.
- При отмене какого-либо действия или при прерывании работы, собщения о возврате к работе теперь будут более прозрачные для каждого режима.

### 2.6.5

- Починено повреждение текущего вводимого обращения в момент, когда прилетает просьба ввести капчу и пользователь выбирает отменить обращение вместо ввода капчи.

### 2.6.4

- При вводе даты теперь можно время вводить через точку или запятую.
- Небольшое повышение надежности.

### 2.6.3

- Уточнены тексты некоторых сообщений от бота для большей ясности.

### 2.6.2

- Обновлены зависимости.

### 2.6.1

- Исправлен race condition при быстром добавлении фотографий нарушений.
- Примером адреса нарушения стал Брест вместо Минска.

### 2.6.0

- Новый механизм повторной отправки обращений, по идее более надежный. Бонусом возможность повторно отправить уже отправленное обращение (может быть, в случае неудачной отправки ботом).

### 2.5.0

- Теперь при вводе места нарушения бот предлагает выбрать 5 последних введенных адресов.

### 2.4.0

- Новый интерфейс для ввода даты нарушения. По умолчанию подставляется дата сегодня и остается ввести время в достаточно вольном формате.

### 2.3.1

- Исправление ошибок.
- Более надежный старт.
- Ленивые очереди в RabbitMQ чтобы они переживали рестарты (но все равно вроде не переживают).
- [Отправитель] Исправление ошибок.
- [Отправитель] Более надежный старт.
- [Отправитель] Значительно повышена скорость отправки.

### 2.3.0

- Переписана реализация стека состояний. В итоге бот немного осмысленнее сообщает об возврате в предыдущий режим.
- Хостинг telegra.ph внезапно начал иногда отдавать 500 при загрузке фото, приходится пробовать еще.
- Добавлено отображение примечания в тексте об отправке нарушения.

### 2.2.1

- [Отправитель] Много разных ухищрений, чтобы отправитель работал стабильно.
- Изменен текст приглашения для ввода капчи (в соответствии с новой капчей сайта МВД).

### 2.2.0

- [Отправитель] Изменена архитектура отправителя обращений. Отправитель теперь умеет работать с очередью обращений.
- Таймер ввода капчи перенесен в отправителя.

### 2.1.3

- Исправлена ошибка когда не удалялись временные файлы при отмене отправки обращения.

### 2.1.2

- Исправлена ошибка, когда перед постингом в канал буквы номера не заменялись на латинские.
- Обновлено Readme
- Повышена стабильность при смене языка бота или обращения
- [Отправитель] Если из ящика было взято недействительное обращение, то отправитель сходит за актуальным, а не упадет как раньше.

### 2.1.1

- [Отправитель] Повышена стабильность отправителей обращений, они теперь не бросаются отправлять два обращения одновременно.

### 2.1.0

- Добавлена возможность ввести номер телефона в личные данные.

### 2.0.10

- Починена ошибка неопределения адреса по локации.

### 2.0.9

- Добавлено [руководство для разработчика](docs/russian/developers_guide.md) паркун бота.
- Добавлено [немного про архитектуру бота](docs/russian/parkun_arch.md).
- Добавлено предупреждение о регистрозависимости капчи.
- Мелкие доработки.

### 2.0.8

- Доработки для более легкого разворачивания бота на сервере.

### 2.0.7

- Исправлена ошибка с пересохранением уже сохраненного обращения.

### 2.0.6

- Исправлена ошибка отваливающегося таймера отмены обращения.

### 2.0.5

- Добавлено притормаживание после кнопки отправить. Торжественно клянусь его когда-нибудь убрать.
- Исправление ошибок. Повышение стабильности работы бота.

### 2.0.4

- Исправление мелких ошибок.

### 2.0.3

- Обновлены ссылки на инструкцию по эксплуатации.
- Исправление мелких ошибок.

### 2.0.2

- При вводе личных данных бот теперь валидирует номер дома.
- Корпус предлагается ввести раньше дома, чтобы было понятно, что его не надо вводить вместе с домом.

### 2.0.1

- Баг когда бот не приветствовал пользователей старого бота в себе новом.

### 2.0

- Посылка обращений в ГАИ возвращена. [Подробности.](./docs/russian/parkun_2_announcement.md)

### 1.12.0

- Отключена посылка обращений. [Подробности](https://telegra.ph/Pochemu-bot-bolshe-ne-otpravlyaet-ehlektronnye-obrashcheniya-07-03).
    Вся остальная функциональность оставлена.

### 1.11.0

- При вводе личных данных теперь отображается текущее значение.
- Сообщение запроса ФИО согласовано с примером.

### 1.10.8

- Обращение дополнено требованием не выдавать персональные данные заявителя.

### 1.10.7

- Исправление письма обращения в соответствии с новым постановлением МВД от 08.01.2019 №5.
- Изменен адрес почты Гомельского УВД.

### 1.10.6

- Установлено ограничение в 10 фото на одно обращение.
- Мелкие исправления.

### 1.10.5

- Увеличение надежности при старте бота.

### 1.10.4

- Новые email для Гродненской и Витебской области.

### 1.10.3

- Была написана новая инструкция по отправке нарушений. Добавлена в раздел /help и отображается после каждой смены личных данных.

### 1.10.2

- В тело письма теперь явно добавляется email отправителя.

### 1.10.1

- В сообщение перед отправкой добавлена информация о твиттере.

### 1.10.0

- Бот теперь отправляет нарушения и в твиттер.
- Возможно починилось периодическое дублирование некоторых постов в канале при отправке обращения ботом.

### 1.9.5

- Сервер верификации адреса почты теперь получает информацию о языке бота.

### 1.9.4

- Уточнили сообщение о подтверждении ящика чтобы было понятно, что нарушение нужно вводить заново.

### 1.9.3

- Мелкие улучшения.

### 1.9.2

- Исправлена ошибка.

### 1.9.1

- Для удобства инспекторов ссылки на фото в обращении теперь озаглавлены и расположены компактно группой.
- Повышение надежности работы бота.

### 1.9.0

- Бот теперь умеет банить и разбанивать.

### 1.8.1

- В тело письма, наряду с фото нарушения, встраивается и ссылка на это фото текстом.
- На соединение для загрузки границ регионов повешен таймаут 5 сек.
- На беларуский язык переведена фраза "Не получилось подобрать адрес."
- Ускорена обработка отправленных боту фотографий.

### 1.8.0

- Беларуская мова у боце.

### 1.7.3

- Баг на айфонах. При нажатии на кнопку "Подтвердить email" отправляется много писем.

### 1.7.2

- Теперь бот шлет копию не на почтовый ящик пользователя, а файлом в чат.

### 1.7.1

- Добавлена проверка, является ли email временным, а не постоянным.

### 1.7.0

- Добавлена процедура верификации ящика электронной почты.

### 1.6.4

- Больше важного текста выделено жирным шрифтом.
- Теперь бот посылает нарушение в канал только после успешной отправки обращения по почте.

### 1.6.3

- Уточнено сообщение о необходимости посылки качественных фото, на которых хорошо видно номер и нарушение.

### 1.6.2

- Теперь обращение просит отвечать на него только по электронной почте. Чтобы спасти побольше деревьев.
- Дополнен хелп информацией о возможности ограниченного пакетного ввода нарушений.

### 1.6.1

- Мелкие улучшения.

### 1.6.0

- Добавлена возможность просмотра и изменения личной информации командой /personal_info. Команда /setup_sender удалена.

### 1.5.1

- Исправлена ошибка неработоспособности бота при некоторых сложных email адресах отправителей.

### 1.5.0

- Добавлена возможность при отправке нарушения указать примечание в письме, от отправителя письма.

### 1.4.3

- Добавлено сообщение о том, что на фото должно быть четко видно гос. номер и само нарушение.
- В процессе повышения регистра и замены латинских букв кириллицей при обработке гос. номера теперь буква "i" тоже заменяется.

### 1.4.2

- При вводе нарушения появилась возможность выбрать адрес, введенный в прошлый раз.
- Изменен способ ответа на обращения (для ответчика).

### 1.4.1

- Смена хостинга для встроенных в тело письма фоток.

### 1.4.0

- Предварительный просмотр перед отправкой теперь формируется вместо с фотографиями нарушения.
- В предварительном просмотре перед отправкой добавлена информация о публикации в канале.
- В тексте предварительного просмотра перед отправкой важная информация выделена жирным шрифтом.
- В канал теперь публикуется также гос. номер (чтобы можно было использовать поиск).

### 1.3.3

- Ошибка в шаблоне - упоминание ГУВД Мингорисполкома.

### 1.3.2

- В альбомах, посылаемых в канал, подпись устанавливается только на первое фото. В таком случае она отображается под альбомом.

### 1.3.1

- Исправлена ошибка, из-за которой бот застревал на отправке фото.

### 1.3.0

- Теперь бот пересылает фотографии, адрес нарушения и время в канал для всеобщей потехи.
- Обновлен /help.

### 1.2.0

- Добавлена возможность отправлять обращения о нарушениях по всей республике. Обращение идет в областное УВД (должны сами пересылать по районам по идее).

### 1.1.6

- В сообщение бота, что обращение успешно отправлено, добавлено предупреждение, что на mail.ru копии письма не доходят.

### 1.1.5

- Дополнен хелп про недоход писем на ящики на mail.ru.
- Дополнен хелп списком изменений.

### 1.1.4

- Прикрепленные в письме фото дополнительно встраиваются в тело письма. Некоторые почтовые ящики ГАИ не умеют прикрепленные файлы.

### 1.1.3

- Исправлен баг, когда добавлялись не все фото при добавлении их группой.

### 1.1.2

- Мелкие доработки под капотом

### 1.1.1

- Обновлен раздел /help

### 1.1.0

- Добавлена возможность отправлять запросы в ГАИ на беларуском языке.
- Исправлена редкая ошибка непоявления подтверждения отправки обращения.

### 1.0.0 Бот запущен в промышленную эксплуатацию

- исправление опечаток в шаблоне письма
- доработка логгирования

### 0.2.0

- Кнопка для переввода данных о нарушении
- Реплики бота стали более официальными

### 0.1.1

- Поправил ошибку неправильного подбора текущего времени.

### 0.1.0 Вторая тестовая версия

- Поправил и изменил много где тексты.
- Добавил команду для фидбэка.
- Сделал кнопки под сообщениями и насыпал их побольше.
- Добавил политику конфиденциальности, почитать можно по команде /help.
- Добавил возможность задавать адрес отправкой локации.
- Сделал номер телефона необязательным.

### 0.0.0 Первая тестовая версия
