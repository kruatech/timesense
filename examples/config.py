"""Пример кастомной конфигурации TimeConfig (только реально работающие параметры)."""
from datetime import datetime
from timesense import TimeSenseParser, TimeConfig

NOW = datetime(2026, 2, 14, 14, 0)


def hr(p, t):
    r = p.parse(t, now=NOW)
    return r.human_readable() if r else "—"


# 1) default_hour_for_one: "в час" → выбранный час
p_default = TimeSenseParser(TimeConfig(default_hour_for_one=13))
p_strict = TimeSenseParser(TimeConfig.strict())   # default_hour_for_one=1, prefer_nearest_future=False
print("в час обед | default(13):", hr(p_default, "в час обед"),
      "| strict(1):", hr(p_strict, "в час обед"))

# 2) prefer_nearest_future: сдвигать прошедшее время в ближайшее будущее
print("в час | nearest_future=True:", hr(TimeSenseParser(TimeConfig(prefer_nearest_future=True)), "в час чай"),
      "| False:", hr(TimeSenseParser(TimeConfig(prefer_nearest_future=False)), "в час чай"))

# 3) working_hours: "в рабочее время" → диапазон
p_work = TimeSenseParser(TimeConfig(working_hours={"start": 9, "end": 18}))
print("в рабочее время встреча:", hr(p_work, "в рабочее время встреча"))

# 4) custom_times: свои слова → время. ВАЖНО: значение — кортеж (час, минута)
p_custom = TimeSenseParser(TimeConfig(custom_times={"брифинг": (11, 30)}))
print("custom_times брифинг (11,30):", hr(p_custom, "брифинг команды"))
