import { readFileSync, writeFileSync } from "node:fs"
import { renderToStaticMarkup } from "react-dom/server"
import { Workbench } from "./page"

const shell = readFileSync(new URL("./index.template.html", import.meta.url), "utf8")
const logo = readFileSync(new URL("../assets/branding/Fieldweave.svg", import.meta.url), "utf8")
const brandDefinitions = logo.match(/<defs>[\s\S]*?<\/defs>/)?.[0]
if (!brandDefinitions) throw new Error("Fieldweave.svg is missing brand definitions")

const page = shell.replace("<!-- workbench -->", () => renderToStaticMarkup(<Workbench brandDefinitions={brandDefinitions} />))
writeFileSync(new URL("../dist/index.html", import.meta.url), page)
