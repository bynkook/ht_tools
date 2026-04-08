export const normalizeSseEvent = (parsed) => {
  const eventType = parsed.event_type ?? parsed.eventType;

  if (eventType === 'system_log') {
    return {
      kind: 'system_log',
      message: {
        role: 'system',
        content: parsed.content ?? '',
        metadata: {
          kind: parsed.kind ?? 'system_log',
          level: parsed.level ?? 'info',
          channel: parsed.channel ?? 'system',
          phase: parsed.phase ?? null,
          title: parsed.title ?? null,
          provider: parsed.provider ?? parsed.provider_id ?? parsed.providerId ?? null,
          providerId: parsed.provider_id ?? parsed.providerId ?? parsed.provider ?? null,
          providerDisplayName: parsed.provider_display_name ?? parsed.providerDisplayName ?? null,
          tool: parsed.tool ?? null,
          selectionReason: parsed.selection_reason ?? parsed.selectionReason ?? null,
          selectionRank: parsed.selection_rank ?? parsed.selectionRank ?? null,
          candidateSummary: parsed.candidate_summary ?? parsed.candidateSummary ?? null,
          partialFailure: parsed.partial_failure ?? parsed.partialFailure ?? null,
          raw: parsed.raw ?? null,
          requestId: parsed.request_id ?? parsed.requestId ?? null,
          fingerprint: parsed.fingerprint ?? null,
          repeatCount: parsed.repeat_count ?? parsed.repeatCount ?? 1,
          suppressedCount: parsed.suppressed_count ?? parsed.suppressedCount ?? 0,
          timestamp: parsed.timestamp ?? null,
          persist: parsed.meta?.persist ?? true,
          rawSuppressed: parsed.meta?.rawSuppressed ?? false,
          rawSuppressedCount: parsed.meta?.rawSuppressedCount ?? 0,
        },
      },
    };
  }

  if (eventType === 'assistant_delta') {
    return {
      kind: 'assistant_delta',
      content: String(parsed.content ?? ''),
    };
  }

  if (eventType === 'assistant_final') {
    return {
      kind: 'assistant_final',
      content: String(parsed.content ?? ''),
    };
  }

  if (eventType === 'stream_end') {
    return {
      kind: 'stream_end',
      finishReason: parsed.finish_reason ?? parsed.finishReason ?? null,
    };
  }

  return {
    kind: 'upstream',
    payload: parsed,
  };
};