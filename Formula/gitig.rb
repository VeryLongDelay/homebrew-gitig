class Gitig < Formula
  include Language::Python::Virtualenv

  desc "Ignorant CLI for generating .gitignore and LICENSE files"
  homepage "https://github.com/verylongdelay/gitig"
  url "https://github.com/VeryLongDelay/gitig/archive/refs/tags/v0.0.2.tar.gz"
  sha256 "1e659c5a0bb432d4d557379dd81c5c930daf31b70f9f2909977a0eb03ee461b5"
  license "MIT"

  depends_on "python@3.13"

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"gitig", "selftest"
    system bin/"gitig", "help"
  end
end

