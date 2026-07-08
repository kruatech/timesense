"""Извлечение локации: в офисе, на работе"""

from ..dict.keywords import Keywords


class LocationExtractor:
    """Post-processor: extracts location from text"""

    @staticmethod
    def extract(tokens, date_token_spans):
        """Extract location phrases not overlapping with date tokens.

        Маркер локации считается локацией только если ему предшествует предлог
        локации (в/во/на/у/около). Без предлога ('в 19 кино') слово остаётся
        частью названия события, а не локацией.
        """
        loc_preps = ["в", "во", "на", "у", "около"]
        for i, t in enumerate(tokens):
            if t.value.lower() in Keywords.LOCATION_MARKERS:
                inside = False
                for s, e in date_token_spans:
                    if s <= t.start <= e:
                        inside = True
                        break
                if inside:
                    continue
                if not (i > 0 and tokens[i - 1].value.lower() in loc_preps):
                    continue
                loc_parts = [tokens[i - 1].value, t.value]
                if i + 1 < len(tokens):
                    nv = tokens[i + 1].value
                    if nv[0:1].isupper() and not any(
                        s <= tokens[i + 1].start <= e for s, e in date_token_spans
                    ):
                        loc_parts.append(nv)
                return " ".join(loc_parts)
        return None
