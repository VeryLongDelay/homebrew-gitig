class Gitig < Formula
  desc "CLI for generating and managing .gitignore files"
  homepage "https://www.npmjs.com/package/gitig"
  url "https://registry.npmjs.org/gitig/-/gitig-__VERSION__.tgz"
  sha256 "__SHA256__"
  license "MIT"

  depends_on "node"

  def install
    libexec.install Dir["*"]
    (bin/"gitig").write_env_script libexec/"package/dist/gitig.js", {
      "PATH" => "#{Formula["node"].opt_bin}:#{ENV["PATH"]}"
    }
  end

  test do
    output = shell_output("#{bin}/gitig help")
    assert_match "gitig", output
  end
end
