NAME = stacksTUI
VERSION = 1.0.0a1
ARCHIVE = $(NAME)-$(VERSION).tar.gz
PREFIX = $(NAME)-$(VERSION)

.PHONY: all archive pkg clean

all: archive pkg

archive:
	git archive --format=tar.gz --prefix=$(PREFIX)/ HEAD > $(ARCHIVE)
	@echo "✅ Created archive: $(ARCHIVE)"

pkg: archive
	makepkg -si

clean:
	rm -f $(ARCHIVE)
	rm -rf pkg
	rm -rf src/$(PREFIX)
	rm -rf src/$(ARCHIVE)
	rm -f *.pkg.tar.zst
	@echo "🧹 Cleaned up build artifacts"

run:
	PYTHONPATH=src python -m stacksTUI

time:
	sh -c "time PYTHONPATH=src python -m stacksTUI"
