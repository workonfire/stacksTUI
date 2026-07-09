# Maintainer: workonfire <kolucki62@gmail.com>

pkgname=stacksTUI
pkgver=1.0.0a1
pkgrel=1
pkgdesc="Textual interface for the stackslib card game engine"
arch=('any')
url="https://github.com/workonfire/stacksTUI"
license=('GPL-3.0-or-later')
depends=('python' 'python-stackslib' 'python-rich' 'python-textual' 'python-websockets')
makedepends=('python-build' 'python-installer' 'python-wheel' 'python-hatchling')
source=("${pkgname}-${pkgver}.tar.gz::${url}/archive/refs/tags/v${pkgver}.tar.gz")
sha256sums=('SKIP')

build() {
	cd "$srcdir/${pkgname}-${pkgver}"
	python -m build --wheel --no-isolation
}

package() {
	cd "$srcdir/${pkgname}-${pkgver}"
	python -m installer --destdir="$pkgdir" dist/*.whl
	install -Dm644 LICENSE "$pkgdir/usr/share/licenses/${pkgname}/LICENSE"
}
