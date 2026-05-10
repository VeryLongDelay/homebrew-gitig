class Gitig < Formula
  include Language::Python::Virtualenv

  desc "Ignorant CLI for generating .gitignore and LICENSE files"
  homepage "https://github.com/verylongdelay/gitig"
  url "https://github.com/VeryLongDelay/gitig/archive/refs/tags/v0.0.1.tar.gz"
  sha256 "e066d693c92505419f3cdc824d5d80fc72b0a24194dd9eb08ac87c4232428256"
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

