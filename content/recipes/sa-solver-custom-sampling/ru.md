# SA-Solver с интервалом SDE 20–80%

Fragment сохраняет defaults `SamplerSASolver`: eta 1, stochastic interval 0.2–0.8, `s_noise 1`, predictor order 3, corrector order 4, PECE и simplified order 2 выключены.

## Подключение

Подайте MODEL в конструктор tau. GUIDER во внешнем порту sampler должен использовать ту же модельную конфигурацию. Затем добавьте NOISE, SIGMAS и LATENT. Формат fragment не может доказать равенство двух модельных путей, поэтому проверьте это в графе.

## Что проверено

Порты и settings сверены с `/object_info`. Exact-source probe переводит проценты в sigma и проверяет inclusive tau-интервал. В official templates 0.1.42 нода не встречается; sampling с весами не выполнялся.

## На что обратить внимание

Проценты не создают SIGMAS. Если поменять start/end местами, tau может оставаться нулём всю траекторию. Включение PECE добавляет model evaluations на шагах с corrector.
