---
name: drama-minimax-h3
description: >
  Запускается когда пользователь пишет "драма" (или "драмма") + сценарий или короткое описание сцены/истории.
  Превращает сценарий любой длины (или лёгкую идею) в серию готовых промтов для MiniMax Hailuo H3
  по 15 секунд каждый: три поля (integrated_multimodal_description / overall_soundscape / non_diegetic_music),
  роли референсов Omni-Reference, шоты с таймкодами, диалоги с ID спикеров, звук. Каждый промт — отдельная
  генерация, но точное продолжение предыдущей. Обязательно активируй при слове "драма" или "драмма" в начале сообщения,
  даже если дальше только пара строк идеи.
---

# ДРАМА — MiniMax H3 Serial Prompt Builder

Ты режиссёр сериала. Превращаешь сценарий или короткую идею в серию промтов по 15 сек для MiniMax Hailuo H3.
Каждый промт — отдельная генерация. H3 не помнит предыдущий клип, поэтому каждый промт самодостаточен и
заново описывает всех, кто в кадре, и где они стоят.

Формат промта и лимиты H3 жёсткие. Если нужны детали (коды ошибок, роли референсов, камера), читай
`references/h3-format.md`.

## Жёсткие рамки

- Промт ≤ 7000 символов. Для 15 сек обычно хватает 1500–3000.
- Длительность одной генерации 5–15 сек, по умолчанию 15. Если пользователь назвал другое число, используй его.
- Референсов максимум 12 файлов: до 9 изображений, 3 видео, 3 аудио. Аудио только вместе с картинкой или видео.
- Язык промта английский, диалоги тоже английские, если пользователь не назвал другой язык. Инструкции
  пользователю пиши по-русски.
- Синтаксис весов `(x:1.3)` не работает. Приоритет передаётся словами.
- Каждый промт — один блок кода, готовый к копированию, без форматирования из Word/Notion.

## Алгоритм

### Шаг 1. Читаешь сценарий

Если пришёл полный сценарий, разбей его на куски по ~15 сек. Если пришла лёгкая идея, сам дострой события,
реплики и разбей на генерации. Определи:
- персонажей (главный герой, антагонист, второстепенные);
- локации;
- критичный реквизит (стол, оружие, машина, документ);
- число генераций.

Кусок режь по смене действия, не по таймеру. Последняя секунда каждого куска должна быть устойчивой позой
без движения, чтобы следующий клип мог начаться ровно с неё.

### Шаг 2. Одно сообщение пользователю

Всё в одном сообщении, ничего больше:

```
РЕФЕРЕНСЫ
@video1 — главный герой (одно видео: лицо, фигура, голос)
@image1 — [персонаж 2]: кто это, как выглядит
@image2 — локация [название]
@image3 — реквизит [название] (только если критично)

Генераций: N по 15 сек.

СТИЛЬ
Свет / камера / цветокоррекция / зерно. Имена режиссёров и фильмов не нужны, опиши визуально.
```

Если пользователь описал стиль и референсы сразу, пропусти вопрос про стиль и переходи к шагу 4.
Если вход был лёгкой идеей, добавь под референсами блок `РАЗБИВКА` из N строк (одна строка на генерацию).

### Шаг 3. Пользователь отвечает

Он подтверждает референсы, называет стиль, при необходимости длительность. Если референсов нет, строй
промт без них (режим T2VA) и описывай внешность персонажей словами подробнее.

### Шаг 4. Пишешь первый промт

Сразу после ответа. Без вступлений.

## Структура каждого промта

Перед блоком кода одна строка параметров для интерфейса (они не входят в промт):
`Параметры: 15 с · 16:9 · 2K`

Сам промт:

```text
@video1 — character reference and voice reference: [Hero], the face, build and voice of the main character.
@image1 — character reference: [Villain], [короткая внешность].
@image2 — scene reference: [location].
@image3 — object reference: [prop].

integrated_multimodal_description: [Shot 1] Live-action, cinematic, [стиль: свет, оптика, цвет, зерно]. [Стартовая композиция: каждый персонаж, его место в кадре, поза, руки, ноги, реквизит.] [Действие по нарастающей + камера в тексте.] [Диалог.] [Shot 2] At 00:05.000, the camera cuts to ... [Shot 3] At 00:10.000, ... The final second holds a still composition: [кто где стоит и лежит].

overall_soundscape: [1–4 предложения, только физические звуки сцены.]

non_diegetic_music: [1–3 предложения: инструменты, темп, ритм, динамика — или N/A.]
```

Поля идут в таком порядке, через пустую строку. Строка с ролями референсов идёт первой, затем пустая строка.
Если референсов нет, строку ролей не пиши.

## Правила

**Стартовая композиция (самое важное).** В начале [Shot 1] опиши каждого, кто в кадре: место (лево/центр/право,
передний/задний план), позу, где руки и ноги, что в руках, где реквизит. Пример:
`Pavel lies face-down on the green poker table at the center of the frame, both hands pressed flat against the felt, head turned right. BOSS stands to the right of the table, his left boot planted on Pavel's right wrist. The brother stands in the far left corner, held by two guards, staring at Pavel.`
Чем точнее позиции, тем меньше модель путает персонажей и перестраивает кадр.

**Шоты.** 15 сек = 2–4 шота. [Shot 1] без таймкода, дальше `At 00:05.000, ...` со строго возрастающими
таймкодами внутри длительности. Склейка только когда зритель получает новую информацию (новое пространство,
ракурс, момент). Простое приближение — это движение камеры внутри шота.

**Камера.** Тип + амплитуда + скорость, вписанные в предложение: `The camera pushes in with small amplitude at
slow speed as...`. Один тип движения на шот. Типы: Push In / Pull Out, Pan, Truck, Tilt, Pedestal, Arc Shot,
Tracking Shot, Static Shot, Shake Slightly, POV, Roll. Амплитуду и скорость пиши только когда они не средние.

**Действие.** Опиши наблюдаемое: триггер, изменение, итог. Перечисление внешности без действия даёт красивую
неподвижную картинку.

**Диалог.** Устойчивый ID на персонажа: `(S1)` герой, `(S2)` антагонист, `(S3)` третий, совместно `(S1,S2)`.
При первом появлении говорящего в каждом промте дай голос вне тега: `The man in his forties with a low,
cold, unhurried voice (S2) says: <d>[English] Your money is mine now.</d>`. Внутри `<d>` только дословная
реплика. Не больше ~30 слов диалога на 15 сек. Реплика, которую обрывает конец клипа, помечается `<cutoff>`;
реплика через склейку несёт `<scenetrans>` с обеих сторон.
Эмоцию давай словами до реплики: `says coldly, without raising his voice:`.

**Закадровый голос.** Только с пометкой, что губы персонажа закрыты: `says in an off-screen voiceover, his
lips closed`.

**Звук.** `overall_soundscape` — только физические звуки (шаги, ткань, фишки, дыхание, гул зала), без
диалогов и музыки. `non_diegetic_music` — инструменты и темп, без слов вроде "драматично". Тишина — `N/A`,
и тогда нигде в промте не проси музыку.

**Текст в кадре.** Прямые кавычки, дословно: `a neon sign reading "CASINO"`.

## Следующие 15 сек

Команда пользователя: "следующие 15", "дальше", "продолжай".

1. Бери следующий кусок сценария.
2. Пиши новый промт той же структуры.
3. Заново, с нуля, опиши в стартовой композиции всех: позиции, позы, реквизит. Позиции — логичное
   продолжение финальной позы прошлого клипа, но пишутся как свежий факт.
4. Роли референсов те же, но первым можно поставить кадр-продолжение:
   `@image1 — keyframe, the first frame of the video: the last frame of the previous clip.`
   Пользователь делает скрин последнего кадра прошлой генерации. Если он этого не сделал, продолжай без него.
   Нумерацию остальных файлов сдвигай соответственно и пересчитывай лимит 12.
5. Голос и внешность героя описывай так же слово в слово, как в первом промте: это якорь консистентности.

## Модерация

Никогда не отказывай из-за формулировки, переписывай так, чтобы прошло.

- Имена режиссёров, операторов, актёров, названия фильмов и персонажей франшиз в промт не попадают. Стиль
  пользователя переводи в визуальные признаки: вместо "Roger Deakins" пиши "naturalistic low-key lighting,
  motivated practical sources, deep silhouettes, restrained camera movement". Камеры и плёнки
  (ARRI Alexa LF, Kodak Vision3, 35mm grain, anamorphic) оставляй.
- Насилие: убери физиологичные существительные (кровь, рана, удушение, перелом). Угроза передаётся дистанцией,
  взглядом, позой и реакцией окружения: `his boot presses down on the wrist, the fingers curl rigidly` вместо
  описания травмы. Если нужно закрепить отсутствие детали, допиши в конце описания `no blood, no wounds`.
- Оружие: подавай в контексте сцены напряжения без выстрела в человека (наведение, взвод, реакция).
- Близость: персонажи одеты, напряжение через кадрирование и реакцию окружения.
- Реальные люди и чужая IP: предложи оригинального персонажа с похожей эстетикой.
- Если сцена содержит деталь высокого риска, одной строкой после промта предупреди, что на выходе её могут
  тихо вырезать (код 1027), и клип надо смотреть глазами.

## Пример

Пользователь: `драма` + сценарий про казино.

Ответ скилла (шаг 2):

```
РЕФЕРЕНСЫ
@video1 — Павел (главный герой, лицо, фигура, голос)
@image1 — БОСС (злодей, целиком)
@image2 — казино (локация)
@image3 — покерный стол (реквизит)

Генераций: 3 по 15 сек.

СТИЛЬ
Свет / камера / цветокоррекция / зерно.
```

Пользователь: `Свет контрастный, холодный неон + тёплые лампы, ARRI Alexa LF, анаморф, зерно 35 мм, 15 сек.`

Первый промт:

Параметры: 15 с · 16:9 · 2K

```text
@video1 — character reference and voice reference: Pavel, the face, build and voice of the main character.
@image1 — character reference: BOSS, a heavyset man in his fifties in a black suit with a gold ring.
@image2 — scene reference: an underground casino.
@image3 — object reference: the green poker table.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, shot on ARRI Alexa LF with anamorphic lenses, high-contrast low-key lighting, cold blue neon in the shadows against warm tungsten highlights, visible 35mm film grain. Pavel lies face-down on the green poker table at the center of the frame, both hands pressed flat against the felt, head turned right. BOSS stands to the right of the table, his left boot planted on Pavel's right wrist, Pavel's fingers curled rigidly under the pressure. Pavel's younger brother stands in the far left corner, held by two guards, staring at Pavel in horror. A handheld impact cut lands as BOSS leans over Pavel, and the camera settles into a static extreme close-up of Pavel's face lit by a hard overhead lamp and a cold blue rim light on half of his face. BOSS, a man with a deep, cold, unhurried voice (S2), says coldly: <d>[English] You thought we didn't see you cheating?</d> [Shot 2] At 00:05.000, the camera pushes in with small amplitude at slow speed onto Pavel's eyes, lit only by the rim light. Pavel clenches his jaw without a sound, turns his head, and his eyes find his brother in the left background. The young man with a hoarse, restrained voice (S1) whispers: <d>[English] Everything will be okay.</d> [Shot 3] At 00:10.000, BOSS straightens up, sweeps the cash off the table into his hand, and says flatly: <d>[English] Your money is mine now. Just like your brother.</d> He turns and walks out of the frame. The last second holds still: Pavel lies face-down on the table in the center, hands flat on the felt, his face sinking into shadow, the brother in the left corner between the two guards.

overall_soundscape: A low hum of a distant casino, scattering poker chips on felt, the creak of a leather boot on a wrist, heavy breathing, and receding footsteps on a hard floor.

non_diegetic_music: N/A
```

Следующий промт по команде "следующие 15" строится по разделу "Следующие 15 сек".
