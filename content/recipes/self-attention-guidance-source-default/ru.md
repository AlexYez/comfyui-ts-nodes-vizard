# SAG: source-derived runtime defaults

Fragment добавляет `SelfAttentionGuidance` со `scale = 0.5` и `blur_sigma = 2.0`. Он рассчитан на отдельный опыт с 4D image latent, обеими CFG-ветвями и batch size `1`; pinned source предупреждает, что chunked batches обрабатываются ненадёжно.

Не задавайте `blur_sigma = 0`: exact-source probe получил NaN в Gaussian kernel. `scale = 0` тоже не служит дешёвым bypass — attention capture, blur и дополнительный unconditional forward продолжают выполняться.

Официальный wheel 0.1.42 не содержит SAG. Fragment воспроизводит runtime defaults и типы портов, но не включает модель, prompt, sampler или полный workflow; визуальная генерация им не исполнялась.
