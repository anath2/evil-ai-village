#!/usr/bin/env python3
"""Compare actual costs for one fixed inference-only smoke prompt per model."""
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from village.models import AdaptionClient, BudgetExceeded


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / '.env')
    client = AdaptionClient(budget_usd=.01, max_retries=1, timeout=45)
    rows = []
    try:
        response = client._client.get(client._url().rsplit('/', 1)[0] + '/models', headers=client._headers())
        response.raise_for_status()
        for model in response.json()['data']:
            model_id = model['id']
            before = client.total_cost_usd
            tokens_before = (client.total_prompt_tokens, client.total_completion_tokens)
            started = time.monotonic()
            row = {'model': model_id}
            try:
                result = client.chat(model_id, [{'role': 'user', 'content': 'Reply with the single word: ready'}],
                                     temperature=0, max_tokens=1024)
                row.update(ok=result.text.strip().lower() == 'ready', reply=result.text[:200])
            except Exception as error:
                row.update(ok=False, error=str(error))
            row.update(cost_usd=client.total_cost_usd - before,
                       input_tokens=client.total_prompt_tokens - tokens_before[0],
                       output_tokens=client.total_completion_tokens - tokens_before[1],
                       seconds=round(time.monotonic() - started, 2))
            rows.append(row)
            print(json.dumps(row), flush=True)
            if client.budget_exhausted:
                break
    finally:
        client.close()
        output = root / '.village' / 'model-cost-smoke.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        report = {'prompt': 'Reply with the single word: ready', 'max_output_tokens': 1024,
                  'budget_usd': .01, 'total_cost_usd': client.total_cost_usd, 'models': rows,
                  'note': 'Single observed prompt costs, not a model price list or capability benchmark.'}
        output.write_text(json.dumps(report, indent=2))
        print('Saved:', output, flush=True)


if __name__ == '__main__':
    main()
