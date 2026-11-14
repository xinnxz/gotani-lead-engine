# GoTani Lead Agent — UI Asset Pack

Paket aset vektor untuk implementasi ulang UI/UX GoTani Lead Agent.

## Isi
- `logo/`: logo mark dan wordmark GoTani dalam SVG.
- `icons/`: 25 ikon outline SVG yang bisa dipakai untuk sidebar, KPI, tab, filter, dan aksi.
- `illustrations/`: ilustrasi lanskap pertanian untuk hero/banner dashboard.
- `styles/tokens.css`: design tokens warna, radius, border, dan shadow.

## Cara pakai
Aset SVG dapat digunakan langsung melalui tag HTML:

```html
<img src="/assets/logo/gotani-wordmark.svg" alt="GoTani" />
<img src="/assets/illustrations/farm-landscape.svg" alt="" />
```

Untuk ikon, atur warna melalui `color` karena SVG menggunakan `currentColor`:

```html
<img src="/assets/icons/search.svg" alt="" />
```

Jika ingin kontrol warna ikon via CSS, gunakan SVG inline atau komponen icon wrapper.

## Catatan
Ini adalah paket aset UI (bukan screenshot dashboard). Paket ini tidak mengubah atau menghapus fitur, API, state, maupun business logic aplikasi.
