class Gitig < Formula
  include Language::Python::Virtualenv

  desc "Ignorant CLI for generating .gitignore and LICENSE files"
  homepage "https://github.com/verylongdelay/gitig"
  url "https://github.com/verylongdelay/gitig/archive/refs/tags/v0.0.0.tar.gz"
  sha256 "REPLACE_ME"
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

