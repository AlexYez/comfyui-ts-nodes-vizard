# CFGZeroStar перед WAN KSampler

Подайте подготовленный WAN MODEL в `CFGZeroStar`, затем соедините `patched_model` с `KSampler`. Positive, negative и latent должны прийти из совместимой WAN-conditioning цепочки.

Параметры повторяют `wan2.1_fun_control`: seed 887940314022885 в randomize-режиме, 20 steps, cfg 6, UniPC, simple, denoise 1. В соседнем `wan2.1_fun_inp` topology и остальные параметры совпадают, но сохранён другой seed. UI-режим randomize не хранится отдельным полем semantic fragment.

В официальных графах перед CFGZeroStar стоит `UNetTemporalAttentionMultiply`; здесь он оставлен за внешним MODEL-входом. Fragment прошёл schema review, но не импортировался и не выполнялся.
